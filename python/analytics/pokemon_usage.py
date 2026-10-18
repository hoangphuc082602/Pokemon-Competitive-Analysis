"""First aggregate table: pokemon_usage_stats + regulation_totals (definitions: METRICS.md).

    python -m python.analytics.pokemon_usage --output-dir data/output_v2

Population: completed battles of VGC formats (turn_count >= 1, exactly one WIN and one LOSS), one
player-battle per side. Streams battle_team_slot in batches; only small aggregates are kept in memory.
Grain: regulation x rating_band x species_id x poke_id x form_basis ('all' bands are added), where form_basis is
    listed       exact form known from the team preview name
    observed     masked family ('Urshifu-*'), real form seen when the Pokemon entered the field
    unobserved   masked family, never sent out (form unknown; species_id still known)
    species_only form not in the master data (poke_id NULL), e.g. Arceus-Fire
Species-level totals = sum over poke_id / form_basis.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

VGC_PREFIXES = ("gen9vgc", "gen9championsvgc")
BAND_LABELS = ["below_1200", "1200_1399", "1400_1499", "1500_plus"]     # + 'unknown' (NULL rating) and 'all'
Z = 1.959964  # 95% two-sided


def rating_band(rating) -> np.ndarray:
    """Band of each player's own rating_before (the player, not the battle)."""
    values = pd.Series(rating, dtype="float").to_numpy()
    out = np.full(len(values), "unknown", dtype=object)
    known = ~np.isnan(values)
    for lo, hi, label in ((-np.inf, 1200, BAND_LABELS[0]), (1200, 1400, BAND_LABELS[1]),
                          (1400, 1500, BAND_LABELS[2]), (1500, np.inf, BAND_LABELS[3])):
        out[known & (values >= lo) & (values < hi)] = label
    return out


def regulation_of(format_id: pd.Series) -> pd.Series:
    return format_id.str.replace("(bo3)", "", regex=False).str.replace("bo3", "", regex=False)


def wilson(wins: pd.Series, n: pd.Series) -> tuple[pd.Series, pd.Series]:
    """95% Wilson interval for a proportion (vectorised; n == 0 -> NaN)."""
    n = n.astype(float)
    p = (wins / n.where(n > 0)).clip(upper=1)      # wins > n is a data problem reported elsewhere, not a CI
    denom = 1 + Z**2 / n
    centre = (p + Z**2 / (2 * n)) / denom
    half = Z * np.sqrt(p * (1 - p) / n + Z**2 / (4 * n**2)) / denom
    return centre - half, centre + half


def species_labels(name_map: pd.DataFrame) -> dict[int, str]:
    """Readable species label: the shortest Showdown name of the species, without a trailing '-*'."""
    m = name_map.dropna(subset=["species_id"]).copy()
    m["species_id"] = m["species_id"].astype(int)
    m["label"] = m["showdown_name"].astype(str).str.replace("-*", "", regex=False)
    m = m.assign(n=m["label"].str.len()).sort_values(["species_id", "n", "label"])
    return m.drop_duplicates("species_id").set_index("species_id")["label"].to_dict()


def top_species(usage: pd.DataFrame, regulation: str, n: int = 15, band: str = "all") -> pd.DataFrame:
    """Species-level view (all forms together) of one regulation and rating band, most used first."""
    u = usage[(usage["regulation"] == regulation) & (usage["rating_band"] == band)]
    g = u.groupby(["species_id", "species"], as_index=False)[["appearances", "wins", "sent_out", "leads"]].sum()
    g["usage_%"] = (100 * g["appearances"] / u["player_battles"].iloc[0]).round(1)
    g["win_%"] = (100 * g["wins"] / g["appearances"]).round(1)
    g["vs_band_pp"] = (g["win_%"] - 100 * u["wins"].sum() / u["appearances"].sum()).round(1)   # vs all species, same band
    g["sent_out_%"] = (100 * g["sent_out"] / g["appearances"]).round(1)
    g["lead_%"] = (100 * g["leads"] / g["appearances"]).round(1)
    return g.sort_values("appearances", ascending=False).head(n)[
        ["species", "appearances", "usage_%", "win_%", "vs_band_pp", "sent_out_%", "lead_%"]].reset_index(drop=True)


def load_scope(out_dir: Path) -> pd.DataFrame:
    """Completed VGC battles: index battle_id, columns regulation, p1_win."""
    battle = pq.read_table(out_dir / "battle.parquet", columns=["battle_id", "format_id", "turn_count", "upload_time"]).to_pandas()
    battle = battle[battle["format_id"].astype(str).str.startswith(VGC_PREFIXES) & (battle["turn_count"].fillna(0) >= 1)]
    players = pq.read_table(out_dir / "battle_players.parquet",
                            columns=["battle_id", "side", "result", "rating_before", "username"]).to_pandas()
    players = players[players["battle_id"].isin(battle["battle_id"])]
    n = players.groupby("battle_id").size()
    wins = (players["result"] == "WIN").groupby(players["battle_id"]).sum()
    losses = (players["result"] == "LOSS").groupby(players["battle_id"]).sum()
    complete = n.index[(n == 2) & (wins == 1) & (losses == 1)]
    p1_win = set(players.loc[(players["side"] == "p1") & (players["result"] == "WIN"), "battle_id"])
    scope = battle[battle["battle_id"].isin(complete)].copy()
    scope["regulation"] = regulation_of(scope["format_id"].astype(str))
    scope["p1_win"] = scope["battle_id"].isin(p1_win)
    scope["month"] = (pd.to_datetime(scope["upload_time"].astype("float"), unit="s", utc=True, errors="coerce")
                      .dt.strftime("%Y-%m").fillna("unknown"))
    scope = scope.set_index("battle_id")
    for side in ("p1", "p2"):
        r = players.loc[players["side"] == side].set_index("battle_id")["rating_before"].astype("float")
        scope[f"{side}_rating"] = r.groupby(level=0).first().reindex(scope.index).to_numpy()
        u = players.loc[players["side"] == side].set_index("battle_id")["username"].astype(object)
        scope[f"{side}_user"] = u.groupby(level=0).first().reindex(scope.index).to_numpy()
    return scope[["regulation", "month", "p1_win", "p1_rating", "p2_rating", "p1_user", "p2_user"]]


def band_totals(scope: pd.DataFrame) -> pd.DataFrame:
    """Player-battles per regulation and rating band ('all' rows also carry the number of battles)."""
    sides = pd.concat([
        pd.DataFrame({"regulation": scope["regulation"].to_numpy(), "rating_band": rating_band(scope[f"{side}_rating"])})
        for side in ("p1", "p2")])
    t = sides.groupby(["regulation", "rating_band"]).size().rename("player_battles").reset_index()
    total = t.groupby("regulation", as_index=False)["player_battles"].sum().assign(rating_band="all")
    total["battles"] = total["player_battles"] // 2
    out = pd.concat([total, t], ignore_index=True)[["regulation", "rating_band", "battles", "player_battles"]]
    out["battles"] = out["battles"].astype("Int64")
    return out


KEYS = ["regulation", "rating_band", "species_id", "poke_id", "form_basis"]
COUNTS = ["appearances", "wins", "sent_out", "sent_out_wins", "leads"]


def aggregate(team_slot_path: Path, scope: pd.DataFrame, name_map: pd.DataFrame, batch_size: int = 1_000_000):
    """Returns (usage counts per grain, number of in-scope slots whose name is not in the mapping)."""
    index = pd.Index(scope.index.astype(str))
    reg_cat = scope["regulation"].astype("category")
    reg_codes, regs = reg_cat.cat.codes.to_numpy(), reg_cat.cat.categories.to_numpy()
    p1_win = scope["p1_win"].to_numpy()
    p1_rating, p2_rating = scope["p1_rating"].to_numpy(), scope["p2_rating"].to_numpy()
    nm = name_map.drop_duplicates("showdown_name").set_index("showdown_name")
    species_of, poke_of = nm["species_id"].to_dict(), nm["poke_id"].to_dict()

    cols = ["battle_id", "player_side", "pokemon_name", "species_observed", "form_status", "was_sent_out", "is_lead"]
    parts, unmapped = [], 0
    for b in pq.ParquetFile(team_slot_path).iter_batches(columns=cols, batch_size=batch_size):
        df = b.to_pandas()
        pos = index.get_indexer(df["battle_id"].astype(str))
        keep = pos >= 0
        df, pos = df[keep].reset_index(drop=True), pos[keep]
        if df.empty:
            continue
        name, observed, status = df["pokemon_name"].astype(object), df["species_observed"].astype(object), df["form_status"].astype(object)
        form_name = np.where(status == "listed", name, np.where(status == "observed", observed, ""))
        species_id = name.map(species_of)
        poke_id = pd.Series(form_name).map(poke_of)
        unmapped += int(species_id.isna().sum())
        basis = np.where(poke_id.notna(), status, np.where(status.isin(["unobserved", "ambiguous"]), "unobserved", "species_only"))
        is_p1 = df["player_side"].to_numpy() == "p1"
        won = np.where(is_p1, p1_win[pos], ~p1_win[pos])
        band = rating_band(np.where(is_p1, p1_rating[pos], p2_rating[pos]))
        sent = df["was_sent_out"].fillna(0).astype(int).to_numpy()
        part = pd.DataFrame({
            "regulation": regs[reg_codes[pos]], "rating_band": band, "species_id": species_id.to_numpy(), "poke_id": poke_id.to_numpy(),
            "form_basis": basis, "appearances": 1, "wins": won.astype(int),
            "sent_out": sent, "sent_out_wins": sent * won.astype(int), "leads": df["is_lead"].fillna(0).astype(int).to_numpy(),
        })
        part = part[part["species_id"].notna()]
        parts.append(part.groupby(KEYS, dropna=False, as_index=False).sum())
    usage = pd.concat(parts, ignore_index=True).groupby(KEYS, dropna=False, as_index=False).sum()
    return usage, unmapped


def build_tables(out_dir: Path, name_map: pd.DataFrame, batch_size: int = 1_000_000):
    scope = load_scope(out_dir)
    totals = band_totals(scope)
    usage, unmapped = aggregate(out_dir / "battle_team_slot.parquet", scope, name_map, batch_size)
    every = usage.groupby([k for k in KEYS if k != "rating_band"], dropna=False, as_index=False)[COUNTS].sum()
    usage = pd.concat([every.assign(rating_band="all"), usage], ignore_index=True)
    usage = usage.merge(totals[["regulation", "rating_band", "player_battles"]], on=["regulation", "rating_band"])
    usage["usage_share"] = usage["appearances"] / usage["player_battles"]
    usage["win_rate"] = usage["wins"] / usage["appearances"]
    base = usage.groupby(["regulation", "rating_band"])[["wins", "appearances"]].transform("sum")
    usage["band_win_rate"] = base["wins"] / base["appearances"]        # all species of the same regulation and band
    usage["win_rate_delta"] = usage["win_rate"] - usage["band_win_rate"]
    usage["win_ci_low"], usage["win_ci_high"] = wilson(usage["wins"], usage["appearances"])
    usage["sent_out_rate"] = usage["sent_out"] / usage["appearances"]
    usage["lead_rate"] = usage["leads"] / usage["appearances"]
    for c in ("species_id", "poke_id"):
        usage[c] = usage[c].astype("Int64")
    labels = species_labels(name_map)
    slugs = name_map.dropna(subset=["poke_id"]).drop_duplicates("poke_id").assign(
        poke_id=lambda d: d["poke_id"].astype(int)).set_index("poke_id")["pokemon"].to_dict()
    usage["species"] = usage["species_id"].astype(int).map(labels)
    usage["form"] = usage["poke_id"].map(lambda v: slugs.get(int(v)) if pd.notna(v) else None)
    first = ["regulation", "rating_band", "species", "species_id", "form", "poke_id", "form_basis"]
    usage = usage[first + [c for c in usage.columns if c not in first]]
    return usage.sort_values(["regulation", "rating_band", "appearances"], ascending=[True, True, False]).reset_index(drop=True), totals, unmapped


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output-dir", type=Path, default=Path("data/output"))
    ap.add_argument("--map", type=Path, default=Path("data/mapping/pokemon_name_map.csv"))
    ap.add_argument("--out", type=Path, default=Path("data/aggregates"))
    ap.add_argument("--show", default=None, metavar="REGULATION",
                    help="regulation to print the top species for (default: the one with most battles)")
    ap.add_argument("--band", default="all", choices=["all", "unknown"] + BAND_LABELS, help="rating band for --show")
    ap.add_argument("--to-mysql", action="store_true", help="also (re)write tables pokemon_usage_stats and regulation_totals")
    args = ap.parse_args(argv)

    name_map = pd.read_csv(args.map, dtype={"showdown_name": str})
    usage, totals, unmapped = build_tables(args.output_dir, name_map)
    args.out.mkdir(parents=True, exist_ok=True)
    usage.to_parquet(args.out / "pokemon_usage_stats.parquet", index=False)
    usage.to_csv(args.out / "pokemon_usage_stats.csv", index=False)
    totals.to_csv(args.out / "regulation_totals.csv", index=False)
    print(totals[totals["rating_band"] == "all"].drop(columns="rating_band").to_string(index=False))
    print("\nPlayer-battles per rating band (all regulations):")
    print(totals[totals["rating_band"] != "all"].groupby("rating_band")["player_battles"].sum().to_string())
    print(f"\n{len(usage):,} usage rows; {unmapped:,} in-scope team slots had a name missing from the mapping (excluded)")
    a = usage[usage["rating_band"] == "all"]
    slots, pb = int(a["appearances"].sum()), int(totals.loc[totals["rating_band"] == "all", "player_battles"].sum())
    print(f"checks: average team size {slots / pb:.3f} (expect ~6); win rate over all slots {100 * a['wins'].sum() / slots:.2f}% "
          f"(expect ~50); Pokemon sent out per team {int(a['sent_out'].sum()) / pb:.2f} (expect <= 4)")
    by_band = usage[usage["rating_band"] != "all"].groupby("rating_band")["appearances"].sum()
    print(f"band rows add up to the 'all' rows: {int(by_band.sum()) == slots}")
    reg = args.show or totals[totals["rating_band"] == "all"].sort_values("battles", ascending=False)["regulation"].iloc[0]
    print(f"\nTop species in {reg}, rating band '{args.band}' (all forms together):")
    print(top_species(usage, reg, band=args.band).to_string())
    if args.to_mysql:
        from python.analytics.sql_output import write_table
        from python.database.db_connection import engine
        write_table(usage, "pokemon_usage_stats", engine, [["regulation", "rating_band", "species_id"], ["species_id", "regulation"]])
        write_table(totals, "regulation_totals", engine, [["regulation", "rating_band"]])
        print("Wrote pokemon_usage_stats and regulation_totals to MySQL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())