"""Dimension tables for the dashboard layer: dim_regulation, dim_rating_band, dim_month, dim_species.

    python -m python.analytics.dim_tables --output-dir data/output

They give the BI tool readable labels and a sort order (rating bands and months must not be sorted alphabetically)
and keep the aggregate tables narrow. Built from the same scope as the aggregates (completed VGC battles).
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

from python.analytics.pokemon_usage import BAND_LABELS, load_scope, species_labels

REGULATION_RE = re.compile(r"^gen9(champions)?vgc(\d{4})reg([a-z](?:-[a-z])?)$")
BAND_LIMITS = {"below_1200": (None, 1199), "1200_1399": (1200, 1399), "1400_1499": (1400, 1499), "1500_plus": (1500, None)}


def parse_regulation(regulation: str) -> tuple[str, int | None, str, str]:
    """'gen9vgc2025regi' -> ('Scarlet/Violet', 2025, 'I', 'Reg I 2025'); unknown formats keep the raw id as label."""
    m = REGULATION_RE.match(regulation)
    if not m:
        return "Other", None, "", regulation
    game = "Champions" if m.group(1) else "Scarlet/Violet"
    letter, year = m.group(3).upper(), int(m.group(2))
    return game, year, letter, f"{'Champions ' if m.group(1) else ''}Reg {letter} {year}"


def build_dimensions(out_dir: Path, name_map: pd.DataFrame) -> dict[str, pd.DataFrame]:
    scope = load_scope(out_dir)
    per_month = scope.groupby(["regulation", "month"]).size().rename("battles").reset_index()

    rows = []
    for reg, g in per_month.groupby("regulation"):
        known = g[g["month"] != "unknown"]
        game, year, letter, label = parse_regulation(reg)
        rows.append({"regulation": reg, "label": label, "game": game, "season_year": year, "reg_letter": letter,
                     "first_month": known["month"].min(), "last_month": known["month"].max(),
                     "busiest_month": g.loc[g["battles"].idxmax(), "month"],
                     "battles": int(g["battles"].sum()), "player_battles": int(g["battles"].sum()) * 2})
    # busiest month, not first upload month: late uploads of an old regulation (Reg D) would otherwise sort after newer ones
    regulation = pd.DataFrame(rows).sort_values(["busiest_month", "regulation"]).reset_index(drop=True)
    regulation.insert(1, "sort_order", range(1, len(regulation) + 1))

    band = pd.DataFrame(
        [("all", "All ratings", None, None)] + [(b, b.replace("_", " "), *BAND_LIMITS[b]) for b in BAND_LABELS] + [("unknown", "No rating", None, None)],
        columns=["rating_band", "label", "rating_min", "rating_max"])
    band.insert(1, "sort_order", range(1, len(band) + 1))
    band[["rating_min", "rating_max"]] = band[["rating_min", "rating_max"]].astype("Int64")

    months = sorted(set(per_month["month"]) - {"unknown"})
    month = pd.DataFrame({"month": months})
    start = pd.to_datetime(month["month"] + "-01")
    month["month_start"] = start.dt.date
    month["year"], month["month_number"] = start.dt.year, start.dt.month
    month["label"] = start.dt.strftime("%b %Y")

    masked_species = set(name_map.loc[name_map["form_status"] == "masked", "species_id"].dropna().astype(int))
    labels = species_labels(name_map)
    species = pd.DataFrame({"species_id": list(labels), "species": list(labels.values())}).sort_values("species").reset_index(drop=True)
    species["has_masked_form"] = species["species_id"].isin(masked_species)
    return {"dim_regulation": regulation, "dim_rating_band": band, "dim_month": month, "dim_species": species}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output-dir", type=Path, default=Path("data/output"))
    ap.add_argument("--map", type=Path, default=Path("data/mapping/pokemon_name_map.csv"))
    ap.add_argument("--out", type=Path, default=Path("data/aggregates"))
    ap.add_argument("--to-mysql", action="store_true", help="also (re)write the dim_* tables")
    args = ap.parse_args(argv)

    dims = build_dimensions(args.output_dir, pd.read_csv(args.map, dtype={"showdown_name": str}))
    args.out.mkdir(parents=True, exist_ok=True)
    for name, df in dims.items():
        df.to_csv(args.out / f"{name}.csv", index=False)
        print(f"{name}: {len(df):,} rows")
    print("\n" + dims["dim_regulation"][["sort_order", "label", "first_month", "last_month", "busiest_month", "battles"]].to_string(index=False))
    if args.to_mysql:
        from python.analytics.sql_output import write_table
        from python.database.db_connection import engine
        keys = {"dim_regulation": [["regulation"]], "dim_rating_band": [["rating_band"]], "dim_month": [["month"]], "dim_species": [["species_id"]]}
        for name, df in dims.items():
            write_table(df, name, engine, keys[name])
        print("Wrote the dim_* tables to MySQL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())