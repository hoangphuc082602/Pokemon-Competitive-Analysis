"""Partner frequency and lift between species on the same team (definitions: METRICS.md).

    python -m python.analytics.partner_stats --output-dir data/output --partners Incineroar

Unit: a team = one side of a completed VGC battle (same population as pokemon_usage). Species level (all forms
of a species together). For every pair of species A < B on the same team:
    teams_both = teams containing both            partner_share = teams_both / teams with A (and with B)
    lift = P(A and B) / (P(A) x P(B))             win_rate = wins of those teams / teams_both
Pairs with fewer than --min-support teams are dropped from the output table (counts are exact before that).
Lift only says two species are seen together more or less often than chance, not that they work well together.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from python.analytics.batches import battle_chunks
from python.analytics.pokemon_usage import BAND_LABELS, load_scope, rating_band, species_labels, wilson

BAND_CODES = {label: i for i, label in enumerate(BAND_LABELS + ["unknown"])}
BAND_NAMES = {i: label for label, i in BAND_CODES.items()}
PAIR_KEYS = ["reg", "band", "a", "b"]


def pair_counts(team_slot_path: Path, scope: pd.DataFrame, name_map: pd.DataFrame):
    """Returns (pairs, singles, teams): pair and species team counts per regulation and band, and the team count."""
    index = pd.Index(scope.index.astype(str))
    reg_cat = scope["regulation"].astype("category")
    reg_codes, regs = reg_cat.cat.codes.to_numpy(), reg_cat.cat.categories.to_numpy()
    p1_win, p1_rating, p2_rating = scope["p1_win"].to_numpy(), scope["p1_rating"].to_numpy(), scope["p2_rating"].to_numpy()
    species_of = name_map.drop_duplicates("showdown_name").set_index("showdown_name")["species_id"].to_dict()

    pairs, singles = [], []

    def process(df: pd.DataFrame) -> None:
        pos = index.get_indexer(df["battle_id"].astype(str))
        keep = pos >= 0
        df, pos = df[keep].reset_index(drop=True), pos[keep]
        sid = df["pokemon_name"].astype(object).map(species_of)
        ok = sid.notna().to_numpy()
        df, pos, sid = df[ok], pos[ok], sid[ok].astype(int).to_numpy()
        if len(df) == 0:
            return
        is_p1 = df["player_side"].to_numpy() == "p1"
        band = np.array([BAND_CODES[b] for b in rating_band(np.where(is_p1, p1_rating[pos], p2_rating[pos]))])
        t = pd.DataFrame({"team": pos * 2 + (~is_p1), "sid": sid, "reg": reg_codes[pos], "band": band,
                          "won": np.where(is_p1, p1_win[pos], ~p1_win[pos]).astype(int)}).drop_duplicates(["team", "sid"])
        singles.append(t.groupby(["reg", "band", "sid"], as_index=False).size().rename(columns={"size": "teams"}))
        m = t.merge(t[["team", "sid"]], on="team", suffixes=("_a", "_b"))
        m = m[m["sid_a"] < m["sid_b"]].rename(columns={"sid_a": "a", "sid_b": "b"})
        pairs.append(m.groupby(PAIR_KEYS, as_index=False).agg(teams_both=("won", "size"), wins_both=("won", "sum")))
        if len(pairs) >= 100:                      # keep memory flat
            pairs[:] = [pd.concat(pairs).groupby(PAIR_KEYS, as_index=False).sum()]

    for df in battle_chunks(team_slot_path, ["battle_id", "player_side", "pokemon_name"]):
        process(df)
    pairs = pd.concat(pairs).groupby(PAIR_KEYS, as_index=False).sum()
    singles = pd.concat(singles).groupby(["reg", "band", "sid"], as_index=False).sum()
    teams = pd.DataFrame({"reg": np.repeat(reg_codes, 2), "side_p1": np.tile([True, False], len(scope)),
                          "won": np.column_stack([p1_win, ~p1_win]).ravel().astype(int),
                          "band": np.column_stack([[BAND_CODES[b] for b in rating_band(p1_rating)],
                                                   [BAND_CODES[b] for b in rating_band(p2_rating)]]).ravel()})
    teams = teams.groupby(["reg", "band"], as_index=False).agg(teams=("won", "size"), wins=("won", "sum"))
    return pairs, singles, teams, regs


def build_partner_table(out_dir: Path, name_map: pd.DataFrame, min_support: int = 100):
    scope = load_scope(out_dir)
    pairs, singles, teams, regs = pair_counts(out_dir / "battle_team_slot.parquet", scope, name_map)
    total_pair_events, n_teams = int(pairs["teams_both"].sum()), int(teams["teams"].sum())

    def add_all(df, keys):
        every = df.groupby([k for k in keys if k != "band"], as_index=False).sum().assign(band=-1)
        return pd.concat([every, df], ignore_index=True)

    pairs = add_all(pairs, PAIR_KEYS)
    singles = add_all(singles, ["reg", "band", "sid"])
    teams = add_all(teams, ["reg", "band"])
    pairs = pairs[pairs["teams_both"] >= min_support]
    for side in ("a", "b"):
        pairs = pairs.merge(singles.rename(columns={"sid": side, "teams": f"teams_{side}"}), on=["reg", "band", side])
    pairs = pairs.merge(teams.rename(columns={"teams": "teams_total", "wins": "wins_total"}), on=["reg", "band"])

    labels = species_labels(name_map)
    out = pd.DataFrame({
        "regulation": regs[pairs["reg"].to_numpy()],
        "rating_band": pairs["band"].map(lambda c: "all" if c < 0 else BAND_NAMES[c]),
        "species_a": pairs["a"].map(labels), "species_b": pairs["b"].map(labels),
        "species_a_id": pairs["a"], "species_b_id": pairs["b"],
        "teams_both": pairs["teams_both"], "teams_a": pairs["teams_a"], "teams_b": pairs["teams_b"],
        "teams_total": pairs["teams_total"], "wins_both": pairs["wins_both"]})
    out["share_of_a"] = out["teams_both"] / out["teams_a"]           # P(B | A)
    out["share_of_b"] = out["teams_both"] / out["teams_b"]           # P(A | B)
    out["lift"] = out["teams_both"] * out["teams_total"] / (out["teams_a"] * out["teams_b"])
    out["win_rate"] = out["wins_both"] / out["teams_both"]
    out["win_ci_low"], out["win_ci_high"] = wilson(out["wins_both"], out["teams_both"])
    out["band_win_rate"] = pairs["wins_total"] / pairs["teams_total"]
    out["win_rate_delta"] = out["win_rate"] - out["band_win_rate"]
    out = out.sort_values(["regulation", "rating_band", "teams_both"], ascending=[True, True, False]).reset_index(drop=True)
    return out, total_pair_events / n_teams


def partners_of(table: pd.DataFrame, species: str, regulation: str, band: str = "all", n: int = 15) -> pd.DataFrame:
    t = table[(table["regulation"] == regulation) & (table["rating_band"] == band)]
    mine = t[(t["species_a"] == species) | (t["species_b"] == species)].copy()
    first = mine["species_a"] == species
    mine["partner"] = np.where(first, mine["species_b"], mine["species_a"])
    mine["share_%"] = (100 * np.where(first, mine["share_of_a"], mine["share_of_b"])).round(1)
    mine["win_%"] = (100 * mine["win_rate"]).round(1)
    mine["vs_band_pp"] = (100 * mine["win_rate_delta"]).round(1)
    return mine.sort_values("teams_both", ascending=False).head(n)[["partner", "teams_both", "share_%", "lift", "win_%", "vs_band_pp"]].round(2).reset_index(drop=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output-dir", type=Path, default=Path("data/output"))
    ap.add_argument("--map", type=Path, default=Path("data/mapping/pokemon_name_map.csv"))
    ap.add_argument("--out", type=Path, default=Path("data/aggregates"))
    ap.add_argument("--min-support", type=int, default=100, help="drop pairs seen on fewer teams")
    ap.add_argument("--partners", default="Incineroar", help="species whose partners are printed")
    ap.add_argument("--show", default=None, metavar="REGULATION")
    ap.add_argument("--band", default="all")
    ap.add_argument("--to-mysql", action="store_true", help="also (re)write table pokemon_partner_stats")
    args = ap.parse_args(argv)

    name_map = pd.read_csv(args.map, dtype={"showdown_name": str})
    table, avg_pairs = build_partner_table(args.output_dir, name_map, args.min_support)
    args.out.mkdir(parents=True, exist_ok=True)
    table.to_parquet(args.out / "pokemon_partner_stats.parquet", index=False)
    table.to_csv(args.out / "pokemon_partner_stats.csv", index=False)
    print(f"{len(table):,} partner rows (pairs on at least {args.min_support} teams)")
    print(f"checks: pairs per team {avg_pairs:.2f} (expect ~15 for teams of 6)")
    reg = args.show or table.groupby("regulation")["teams_both"].sum().idxmax()
    print(f"\nPartners of {args.partners} in {reg}, rating band '{args.band}':")
    print(partners_of(table, args.partners, reg, args.band).to_string())
    if args.to_mysql:
        from python.analytics.sql_output import write_table
        from python.database.db_connection import engine
        write_table(table, "pokemon_partner_stats", engine,
                    [["regulation", "rating_band", "species_a_id"], ["regulation", "rating_band", "species_b_id"]])
        print("Wrote pokemon_partner_stats to MySQL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())