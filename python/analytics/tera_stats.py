"""Tera aggregates: pokemon_tera_summary + pokemon_tera_types (definitions: METRICS.md).

    python -m python.analytics.tera_stats --output-dir data/output_v21

Population: the same completed VGC battles as pokemon_usage. A Tera event is attributed to the player who owns
the Pokemon (battle_tera.username) and counted once per player and battle. Denominators come from
data/aggregates/pokemon_usage_stats.parquet (team appearances where the Pokemon entered the field).

pokemon_tera_summary  regulation x rating_band x species: sent_out, tera_events, tera_rate, win rate with / without Tera
pokemon_tera_types    regulation x rating_band x species x tera_type: events, wins, type_share
Win rates are descriptive: players choose when to Terastallize, so the gap is not the effect of Tera.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from python.analytics.pokemon_usage import load_scope, rating_band, species_labels, wilson

EVENT_KEYS = ["regulation", "rating_band", "species_id", "tera_type"]


def tera_events(tera_path: Path, scope: pd.DataFrame, name_map: pd.DataFrame, batch_size: int = 1_000_000):
    """Returns (events per regulation/band/species/type, unmapped species events, events not attributable to a player)."""
    index = pd.Index(scope.index.astype(str))
    reg_cat = scope["regulation"].astype("category")
    reg_codes, regs = reg_cat.cat.codes.to_numpy(), reg_cat.cat.categories.to_numpy()
    p1_win = scope["p1_win"].to_numpy()
    p1_rating, p2_rating = scope["p1_rating"].to_numpy(), scope["p2_rating"].to_numpy()
    p1_user, p2_user = scope["p1_user"].to_numpy(object), scope["p2_user"].to_numpy(object)
    species_of = name_map.drop_duplicates("showdown_name").set_index("showdown_name")["species_id"].to_dict()

    parts, unmapped, unattributed = [], 0, 0
    for b in pq.ParquetFile(tera_path).iter_batches(columns=["battle_id", "username", "species", "tera_type"], batch_size=batch_size):
        df = b.to_pandas()
        pos = index.get_indexer(df["battle_id"].astype(str))
        keep = pos >= 0
        df, pos = df[keep].reset_index(drop=True), pos[keep]
        if df.empty:
            continue
        user = df["username"].astype(object).where(df["username"].notna(), "").to_numpy()
        is_p1, is_p2 = user == p1_user[pos], user == p2_user[pos]
        ok = is_p1 | is_p2
        unattributed += int((~ok).sum())
        df, pos, is_p1 = df[ok].reset_index(drop=True), pos[ok], is_p1[ok]
        first = ~pd.DataFrame({"pos": pos, "side": is_p1}).duplicated().to_numpy()    # one Tera per player and battle
        df, pos, is_p1 = df[first], pos[first], is_p1[first]
        species_id = df["species"].astype(object).map(species_of)
        unmapped += int(species_id.isna().sum())
        won = np.where(is_p1, p1_win[pos], ~p1_win[pos])
        part = pd.DataFrame({
            "regulation": regs[reg_codes[pos]], "rating_band": rating_band(np.where(is_p1, p1_rating[pos], p2_rating[pos])),
            "species_id": species_id.to_numpy(), "tera_type": df["tera_type"].astype(object).to_numpy(),
            "events": 1, "wins": won.astype(int)})
        part = part[part["species_id"].notna()]
        parts.append(part.groupby(EVENT_KEYS, as_index=False).sum())
    events = pd.concat(parts, ignore_index=True).groupby(EVENT_KEYS, as_index=False).sum()
    return events, unmapped, unattributed


def build_tera_tables(out_dir: Path, usage: pd.DataFrame, name_map: pd.DataFrame, batch_size: int = 1_000_000):
    scope = load_scope(out_dir)
    events, unmapped, unattributed = tera_events(out_dir / "battle_tera.parquet", scope, name_map, batch_size)
    events["species_id"] = events["species_id"].astype(int)
    every = events.groupby(["regulation", "species_id", "tera_type"], as_index=False)[["events", "wins"]].sum()
    events = pd.concat([every.assign(rating_band="all"), events], ignore_index=True)

    keys = ["regulation", "rating_band", "species_id"]
    denom = usage.assign(species_id=usage["species_id"].astype(int)).groupby(keys, as_index=False)[["sent_out", "sent_out_wins"]].sum()
    per_species = events.groupby(keys, as_index=False)[["events", "wins"]].sum().rename(
        columns={"events": "tera_events", "wins": "tera_wins"})
    summary = denom.merge(per_species, on=keys, how="left").fillna({"tera_events": 0, "tera_wins": 0})
    summary[["tera_events", "tera_wins"]] = summary[["tera_events", "tera_wins"]].astype(int)
    summary["tera_rate"] = summary["tera_events"] / summary["sent_out"].where(summary["sent_out"] > 0)
    summary["tera_rate_ci_low"], summary["tera_rate_ci_high"] = wilson(summary["tera_events"], summary["sent_out"])
    no_tera = summary["sent_out"] - summary["tera_events"]
    summary["win_rate_tera"] = summary["tera_wins"] / summary["tera_events"].where(summary["tera_events"] > 0)
    summary["win_rate_no_tera"] = (summary["sent_out_wins"] - summary["tera_wins"]) / no_tera.where(no_tera > 0)
    labels = species_labels(name_map)
    summary.insert(2, "species", summary["species_id"].map(labels))

    types = events.merge(per_species, on=keys)
    types["type_share"] = types["events"] / types["tera_events"]
    types.insert(2, "species", types["species_id"].map(labels))
    sort_cols = ["regulation", "rating_band", "tera_events"]
    summary = summary.sort_values(sort_cols, ascending=[True, True, False]).reset_index(drop=True)
    types = types.sort_values(["regulation", "rating_band", "tera_events", "events"], ascending=[True, True, False, False]).reset_index(drop=True)
    return summary, types, unmapped, unattributed


def top_tera(summary: pd.DataFrame, types: pd.DataFrame, regulation: str, band: str = "all", n: int = 15) -> pd.DataFrame:
    s = summary[(summary["regulation"] == regulation) & (summary["rating_band"] == band)]
    s = s[s["tera_events"] > 0].sort_values("tera_events", ascending=False).head(n)
    t = types[(types["regulation"] == regulation) & (types["rating_band"] == band)]
    best = t.sort_values("events", ascending=False).drop_duplicates("species_id").set_index("species_id")
    out = pd.DataFrame({
        "species": s["species"].to_numpy(), "sent_out": s["sent_out"].to_numpy(), "tera_events": s["tera_events"].to_numpy(),
        "tera_%": (100 * s["tera_rate"]).round(1).to_numpy(),
        "top_type": s["species_id"].map(best["tera_type"]).to_numpy(),
        "top_type_%": (100 * s["species_id"].map(best["type_share"])).round(1).to_numpy(),
        "win_tera_%": (100 * s["win_rate_tera"]).round(1).to_numpy(), "win_no_tera_%": (100 * s["win_rate_no_tera"]).round(1).to_numpy()})
    return out.reset_index(drop=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output-dir", type=Path, default=Path("data/output_v21"))
    ap.add_argument("--usage", type=Path, default=Path("data/aggregates/pokemon_usage_stats.parquet"))
    ap.add_argument("--map", type=Path, default=Path("data/mapping/pokemon_name_map.csv"))
    ap.add_argument("--out", type=Path, default=Path("data/aggregates"))
    ap.add_argument("--show", default=None, metavar="REGULATION")
    ap.add_argument("--band", default="all")
    ap.add_argument("--to-mysql", action="store_true", help="also (re)write tables pokemon_tera_summary and pokemon_tera_types")
    args = ap.parse_args(argv)

    name_map = pd.read_csv(args.map, dtype={"showdown_name": str})
    usage = pd.read_parquet(args.usage)
    summary, types, unmapped, unattributed = build_tera_tables(args.output_dir, usage, name_map)
    args.out.mkdir(parents=True, exist_ok=True)
    summary.to_parquet(args.out / "pokemon_tera_summary.parquet", index=False)
    types.to_parquet(args.out / "pokemon_tera_types.parquet", index=False)
    summary.to_csv(args.out / "pokemon_tera_summary.csv", index=False)
    types.to_csv(args.out / "pokemon_tera_types.csv", index=False)

    a = summary[summary["rating_band"] == "all"]
    pb = int(usage[usage["rating_band"] == "all"].drop_duplicates("regulation")["player_battles"].sum())
    print(f"{len(summary):,} summary rows, {len(types):,} type rows; {unmapped:,} Tera events with an unmapped species, "
          f"{unattributed:,} not attributable to a player (both excluded)")
    print(f"checks: Tera events {int(a['tera_events'].sum()):,} over {int(a['sent_out'].sum()):,} sent-out appearances "
          f"({100 * a['tera_events'].sum() / a['sent_out'].sum():.1f}%); at most one Tera per player-battle: "
          f"{int(a['tera_events'].sum()) <= pb}")
    reg = args.show or a.groupby("regulation")["tera_events"].sum().idxmax()
    over = summary[summary["tera_events"] > summary["sent_out"]]
    print(f"summary rows where Tera events exceed sent-out appearances: {len(over):,} (expect 0)")
    if len(over):
        print(over.sort_values("tera_events", ascending=False).head(10)[["regulation", "rating_band", "species", "sent_out", "tera_events"]].to_string(index=False))
    print(f"\nMost Terastallized species in {reg}, rating band '{args.band}':")
    print(top_tera(summary, types, reg, args.band).to_string())
    if args.to_mysql:
        from python.analytics.sql_output import write_table
        from python.database.db_connection import engine
        write_table(summary, "pokemon_tera_summary", engine, [["regulation", "rating_band", "species_id"]])
        write_table(types, "pokemon_tera_types", engine, [["regulation", "rating_band", "species_id"]])
        print("Wrote pokemon_tera_summary and pokemon_tera_types to MySQL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())