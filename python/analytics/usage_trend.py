"""Monthly usage trend per regulation (definitions: METRICS.md): pokemon_usage_monthly + regulation_monthly_totals.

    python -m python.analytics.usage_trend --output-dir data/output_v21 --species Incineroar

Same population as pokemon_usage (completed VGC battles, one row per team). The month is the UTC month of
battle.upload_time, i.e. when the replay was uploaded, which is close to but not exactly when it was played.
Species level (all forms together). Rows of months with few battles are noisy: read them with player_battles.
Grain: regulation x month x rating_band x species_id ('all' bands are added); a player counts in the band of their own
rating_before. `tail` is a regulation-month flag (all bands together) copied to every band of that month.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from python.analytics.pokemon_usage import load_scope, rating_band, species_labels, wilson

TAIL_SHARE = 0.05   # months below 5% of the busiest month of their regulation are flagged `tail`
KEYS = ["regulation", "month", "rating_band", "species_id"]

def monthly_counts(team_slot_path: Path, scope: pd.DataFrame, name_map: pd.DataFrame, batch_size: int = 1_000_000):
    index = pd.Index(scope.index.astype(str))
    reg_cat, month_cat = scope["regulation"].astype("category"), scope["month"].astype("category")
    reg_codes, regs = reg_cat.cat.codes.to_numpy(), reg_cat.cat.categories.to_numpy()
    month_codes, months = month_cat.cat.codes.to_numpy(), month_cat.cat.categories.to_numpy()
    p1_win = scope["p1_win"].to_numpy()
    p1_rating, p2_rating = scope["p1_rating"].to_numpy(), scope["p2_rating"].to_numpy()
    species_of = name_map.drop_duplicates("showdown_name").set_index("showdown_name")["species_id"].to_dict()
    parts = []
    for b in pq.ParquetFile(team_slot_path).iter_batches(columns=["battle_id", "player_side", "pokemon_name", "was_sent_out"], batch_size=batch_size):
        df = b.to_pandas()
        pos = index.get_indexer(df["battle_id"].astype(str))
        keep = pos >= 0
        df, pos = df[keep].reset_index(drop=True), pos[keep]
        sid = df["pokemon_name"].astype(object).map(species_of)
        ok = sid.notna().to_numpy()
        df, pos, sid = df[ok], pos[ok], sid[ok].astype(int).to_numpy()
        if len(df) == 0:
            continue
        is_p1 = df["player_side"].to_numpy() == "p1"
        won = np.where(is_p1, p1_win[pos], ~p1_win[pos]).astype(int)
        part = pd.DataFrame({"regulation": regs[reg_codes[pos]], "month": months[month_codes[pos]],
                             "rating_band": rating_band(np.where(is_p1, p1_rating[pos], p2_rating[pos])), "species_id": sid,
                             "appearances": 1, "wins": won, "sent_out": df["was_sent_out"].fillna(0).astype(int).to_numpy()})
        parts.append(part.groupby(KEYS, as_index=False).sum())
    usage = pd.concat(parts, ignore_index=True).groupby(KEYS, as_index=False).sum()
    every = usage.groupby(["regulation", "month", "species_id"], as_index=False)[["appearances", "wins", "sent_out"]].sum()
    return pd.concat([every.assign(rating_band="all"), usage], ignore_index=True)[KEYS + ["appearances", "wins", "sent_out"]]


def monthly_totals(scope: pd.DataFrame) -> pd.DataFrame:
    """Player-battles per regulation x month x rating band ('all' rows carry battles); `tail` from the 'all' rows."""
    sides = pd.concat([pd.DataFrame({"regulation": scope["regulation"].to_numpy(), "month": scope["month"].to_numpy(),
                                     "rating_band": rating_band(scope[f"{side}_rating"])}) for side in ("p1", "p2")])
    t = sides.groupby(["regulation", "month", "rating_band"]).size().rename("player_battles").reset_index()
    every = scope.groupby(["regulation", "month"]).size().rename("battles").reset_index()
    every["player_battles"] = every["battles"] * 2
    every["share_of_peak"] = every["player_battles"] / every.groupby("regulation")["player_battles"].transform("max")
    every["tail"] = every["share_of_peak"] < TAIL_SHARE      # the format is ending: a different, tiny population
    t = t.merge(every[["regulation", "month", "share_of_peak", "tail"]], on=["regulation", "month"])
    out = pd.concat([every.assign(rating_band="all"), t], ignore_index=True)
    out["battles"] = out["battles"].astype("Int64")
    return out[["regulation", "month", "rating_band", "battles", "player_battles", "share_of_peak", "tail"]]


def build_trend_tables(out_dir: Path, name_map: pd.DataFrame):
    scope = load_scope(out_dir)
    totals = monthly_totals(scope)
    usage = monthly_counts(out_dir / "battle_team_slot.parquet", scope, name_map)
    usage = usage.merge(totals[["regulation", "month", "rating_band", "player_battles", "tail"]],
                        on=["regulation", "month", "rating_band"])
    usage["usage_share"] = usage["appearances"] / usage["player_battles"]
    usage["win_rate"] = usage["wins"] / usage["appearances"]
    usage["win_ci_low"], usage["win_ci_high"] = wilson(usage["wins"], usage["appearances"])
    usage["sent_out_rate"] = usage["sent_out"] / usage["appearances"]
    usage.insert(3, "species", usage["species_id"].map(species_labels(name_map)))
    return (usage.sort_values(["regulation", "month", "rating_band", "appearances"], ascending=[True, True, True, False])
            .reset_index(drop=True),
            totals.sort_values(["regulation", "month", "rating_band"]).reset_index(drop=True))


def species_trend(usage: pd.DataFrame, species: str, regulation: str, band: str = "all") -> pd.DataFrame:
    u = usage[(usage["species"] == species) & (usage["regulation"] == regulation) & (usage["rating_band"] == band)]
    return pd.DataFrame({"month": u["month"], "player_battles": u["player_battles"], "tail": u["tail"], "teams": u["appearances"],
                         "usage_%": (100 * u["usage_share"]).round(1), "win_%": (100 * u["win_rate"]).round(1),
                         "sent_out_%": (100 * u["sent_out_rate"]).round(1)}).sort_values("month").reset_index(drop=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output-dir", type=Path, default=Path("data/output_v21"))
    ap.add_argument("--map", type=Path, default=Path("data/mapping/pokemon_name_map.csv"))
    ap.add_argument("--out", type=Path, default=Path("data/aggregates"))
    ap.add_argument("--species", default="Incineroar")
    ap.add_argument("--show", default=None, metavar="REGULATION")
    ap.add_argument("--to-mysql", action="store_true", help="also (re)write pokemon_usage_monthly and regulation_monthly_totals")
    args = ap.parse_args(argv)

    name_map = pd.read_csv(args.map, dtype={"showdown_name": str})
    usage, totals = build_trend_tables(args.output_dir, name_map)
    args.out.mkdir(parents=True, exist_ok=True)
    usage.to_parquet(args.out / "pokemon_usage_monthly.parquet", index=False)
    usage.to_csv(args.out / "pokemon_usage_monthly.csv", index=False)
    totals.to_csv(args.out / "regulation_monthly_totals.csv", index=False)
    a, ta = usage[usage["rating_band"] == "all"], totals[totals["rating_band"] == "all"]
    print(f"{len(usage):,} usage rows over {len(ta):,} regulation-months x {totals['rating_band'].nunique()} bands; "
          f"months with an unknown upload time: {int((ta['month'] == 'unknown').sum())}")
    slots = int(a["appearances"].sum())
    band_slots = int(usage.loc[usage["rating_band"] != "all", "appearances"].sum())
    band_pb = totals[totals["rating_band"] != "all"].groupby(["regulation", "month"])["player_battles"].sum()
    all_pb = ta.set_index(["regulation", "month"])["player_battles"]
    print(f"checks: average team size {slots / int(ta['player_battles'].sum()):.3f} (expect ~6); "
          f"win rate over all slots {100 * a['wins'].sum() / slots:.2f}% (expect ~50); "
          f"band rows add up to the 'all' rows: {band_slots == slots and band_pb.sort_index().equals(all_pb.sort_index())}; "
          f"tail identical in every band: {int(totals.groupby(['regulation', 'month'])['tail'].nunique().max()) == 1}")
    reg = args.show or ta.groupby("regulation")["battles"].sum().idxmax()
    print(f"\nBattles per month in {reg}:")
    print(ta[ta["regulation"] == reg][["month", "battles", "player_battles", "tail"]].to_string(index=False))
    print(f"\n{args.species} in {reg}:")
    print(species_trend(usage, args.species, reg).to_string(index=False))
    if args.to_mysql:
        from python.analytics.sql_output import write_table
        from python.database.db_connection import engine
        write_table(usage, "pokemon_usage_monthly", engine, [["regulation", "month", "rating_band", "species_id"]])
        write_table(totals, "regulation_monthly_totals", engine, [["regulation", "month", "rating_band"]])
        print("Wrote pokemon_usage_monthly and regulation_monthly_totals to MySQL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())