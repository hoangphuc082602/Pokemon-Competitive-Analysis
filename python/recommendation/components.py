"""Component tables of the v2.0 hybrid recommender (#46), built from Parquet.

Usage component (#50): usage of each species/form per regulation x rating band, with its `n`
(definitions: Metrics.md, pokemon_usage_stats). Same population and grain as
python.analytics.pokemon_usage, which it reuses (team slots streamed in batches; a usage count is per
slot, so it does not need whole battles in one batch).

    python -m python.recommendation.components --output-dir data/output --out data/aggregates
"""
from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from python.analytics.pokemon_usage import build_tables

USAGE_COLUMNS = ["regulation", "rating_band", "species", "species_id", "form", "poke_id", "form_basis",
                 "appearances", "player_battles", "usage_share"]


def usage_component(out_dir: Path, name_map: pd.DataFrame, battle_ids: Iterable | None = None,
                    batch_size: int = 1_000_000) -> pd.DataFrame:
    """One row per regulation x rating band x species_id x poke_id x form_basis.

    `appearances` = team slots with this species/form, i.e. player-battles (species clause: one slot per
    species per team); `player_battles` (the `n`) = player-battles of the regulation and band;
    usage_share = appearances / player_battles. 'all' is its own band, counted from the battles, not
    from the band rows. Rows with n < 100 are kept: this is an input table, the scorer and export hide them.

    battle_ids restricts every count, numerators and `n`, to those battles (the evaluator passes the
    train split only; Bo3 games are not independent, so split by set, not by game). Ids outside the
    population are ignored; a subset with none inside raises ValueError.
    """
    usage, _, _ = build_tables(out_dir, name_map, batch_size, battle_ids=battle_ids)
    return usage[USAGE_COLUMNS].reset_index(drop=True)


def invariants(comp: pd.DataFrame) -> pd.DataFrame:
    """Rows and `n` per regulation x rating band (printed on real data)."""
    return (comp.groupby(["regulation", "rating_band"])
            .agg(rows=("species_id", "size"), player_battles=("player_battles", "first"),
                 n_values=("player_battles", "nunique"), appearances=("appearances", "sum"))
            .reset_index())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Usage component (#50): write it and print rows per regulation and band.")
    ap.add_argument("--output-dir", type=Path, default=Path("data/output"))
    ap.add_argument("--map", type=Path, default=Path("data/mapping/pokemon_name_map.csv"))
    ap.add_argument("--out", type=Path, default=Path("data/aggregates"))
    args = ap.parse_args(argv)
    comp = usage_component(args.output_dir, pd.read_csv(args.map, dtype={"showdown_name": str}))
    args.out.mkdir(parents=True, exist_ok=True)
    comp.to_parquet(args.out / "recommendation_usage_component.parquet", index=False)
    inv = invariants(comp)
    print(inv.to_string(index=False))
    # Consistency check only (not a metric): the band rows, 'all' excluded, must add up to the 'all' row.
    every = inv[inv["rating_band"] == "all"].set_index("regulation")
    bands = inv[inv["rating_band"] != "all"].groupby("regulation")[["player_battles", "appearances"]].sum()
    print(f"\n{len(comp):,} rows; one n per regulation/band: {bool((inv['n_values'] == 1).all())}; "
          f"band n add up to 'all' n: {bool(bands['player_battles'].eq(every['player_battles']).all())}; "
          f"band appearances add up to 'all': {bool(bands['appearances'].eq(every['appearances']).all())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
