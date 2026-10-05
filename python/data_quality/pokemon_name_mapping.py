"""Map Pokémon Showdown names (battle_*.pokemon_name) to PokéAPI master rows (pokemon_stats).

Matching is deliberately conservative:
  1. explicit override  (python/data_quality/showdown_overrides.csv)
  2. exact match after normalisation  ("Flutter Mane" -> "flutter-mane")
Anything else stays UNMATCHED and is reported with *suggestions* only. A suggestion is never applied
automatically, because a wrong silent match (e.g. a regional form mapped to its base form) corrupts every
downstream usage / win-rate statistic.

Run (repo root):  python -m python.data_quality.pokemon_name_mapping --help
"""
from __future__ import annotations

import argparse
import difflib
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd

DEFAULT_OVERRIDES = Path(__file__).with_name("showdown_overrides.csv")
MAP_TABLE = "showdown_pokemon_map"


# ---------------------------------------------------------------- normalisation
def normalize_name(name: str) -> str:
    """'Flutter Mane' -> 'flutter-mane', "Farfetch’d" -> 'farfetchd', 'Type: Null' -> 'type-null'."""
    text = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[.'’:%]", "", text.lower().strip())
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-{2,}", "-", text).strip("-")


# ---------------------------------------------------------------- inputs
def load_overrides(path: Path = DEFAULT_OVERRIDES) -> dict[str, str]:
    """CSV with columns showdown_name,pokemon  ->  {showdown_name: pokeapi_slug}."""
    df = pd.read_csv(path, dtype=str).dropna()
    return {r.showdown_name.strip(): normalize_name(r.pokemon) for r in df.itertuples()}


def count_names_from_parquet(path: Path, column: str = "pokemon_name", batch_size: int = 1_000_000) -> Counter:
    """Count names while streaming ONE column in batches (the real table has ~42M rows)."""
    import pyarrow.parquet as pq

    counts: Counter = Counter()
    for batch in pq.ParquetFile(path).iter_batches(columns=[column], batch_size=batch_size):
        for item in batch.column(0).value_counts().to_pylist():
            counts[item["values"]] += item["counts"]
    counts.pop(None, None)
    return counts


def load_master_names(engine) -> pd.DataFrame:
    return pd.read_sql("SELECT poke_id, pokemon FROM pokemon_stats", engine)


# ---------------------------------------------------------------- core
def build_mapping(counts: Counter, master: pd.DataFrame, overrides: dict[str, str] | None = None):
    """Return (mapping, unmatched). `counts` = {showdown_name: number_of_rows}.

    mapping   : showdown_name, poke_id, pokemon, method ('override' | 'exact'), n_rows
    unmatched : showdown_name, n_rows, suggestions   (sorted by n_rows, biggest first)
    """
    overrides = overrides or {}
    slug_to_row = {}
    for row in master.itertuples():
        slug = normalize_name(row.pokemon)
        if slug in slug_to_row:
            raise ValueError(f"Master data has two rows normalising to '{slug}' - mapping would be ambiguous")
        slug_to_row[slug] = row

    bad = {k: v for k, v in overrides.items() if v not in slug_to_row}
    if bad:
        raise ValueError(f"Overrides point to names that are not in the master data: {bad}")

    mapped, unmatched = [], []
    for name, n_rows in counts.items():
        name = str(name).strip()
        if name in overrides:
            slug, method = overrides[name], "override"
        elif normalize_name(name) in slug_to_row:
            slug, method = normalize_name(name), "exact"
        else:
            slug = None
        if slug is None:
            unmatched.append({"showdown_name": name, "n_rows": n_rows,
                              "suggestions": "; ".join(_suggest(name, slug_to_row))})
        else:
            r = slug_to_row[slug]
            mapped.append({"showdown_name": name, "poke_id": int(r.poke_id), "pokemon": r.pokemon,
                           "method": method, "n_rows": n_rows})

    mapping = pd.DataFrame(mapped, columns=["showdown_name", "poke_id", "pokemon", "method", "n_rows"])
    report = pd.DataFrame(unmatched, columns=["showdown_name", "n_rows", "suggestions"])
    return mapping, report.sort_values("n_rows", ascending=False, ignore_index=True)


def _suggest(name: str, slug_to_row: dict, limit: int = 3) -> list[str]:
    slug = normalize_name(name)
    prefixed = sorted(s for s in slug_to_row if s.startswith(slug + "-"))      # 'mimikyu' -> 'mimikyu-...'
    fuzzy = difflib.get_close_matches(slug, slug_to_row, n=limit, cutoff=0.6)
    return list(dict.fromkeys(prefixed + fuzzy))[:limit]


def coverage(mapping: pd.DataFrame, unmatched: pd.DataFrame) -> dict:
    """Coverage weighted by rows (the denominator that matters for usage / win-rate stats) and by distinct names."""
    rows_ok, rows_bad = int(mapping["n_rows"].sum()), int(unmatched["n_rows"].sum())
    names_ok, names_bad = len(mapping), len(unmatched)
    return {
        "rows_total": rows_ok + rows_bad,
        "rows_matched_pct": round(100 * rows_ok / max(rows_ok + rows_bad, 1), 3),
        "names_total": names_ok + names_bad,
        "names_matched_pct": round(100 * names_ok / max(names_ok + names_bad, 1), 3),
    }


def write_mapping_table(mapping: pd.DataFrame, engine, table: str = MAP_TABLE) -> None:
    """Replace the lookup table (small: one row per distinct Showdown name)."""
    from sqlalchemy import BigInteger, String

    mapping[["showdown_name", "poke_id", "pokemon", "method"]].to_sql(
        table, engine, if_exists="replace", index=False,
        dtype={"showdown_name": String(100), "pokemon": String(100), "method": String(10), "poke_id": BigInteger()},
    )


# ---------------------------------------------------------------- CLI
def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--team-slot", type=Path, default=Path("data/output/battle_team_slot.parquet"))
    ap.add_argument("--column", default="pokemon_name")
    ap.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    ap.add_argument("--out-dir", type=Path, default=Path("data/mapping"))
    ap.add_argument("--to-mysql", action="store_true", help=f"also (re)write table {MAP_TABLE}")
    args = ap.parse_args(argv)

    from python.database.db_connection import engine

    counts = count_names_from_parquet(args.team_slot, args.column)
    mapping, unmatched = build_mapping(counts, load_master_names(engine), load_overrides(args.overrides))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    mapping.to_csv(args.out_dir / "pokemon_name_map.csv", index=False)
    unmatched.to_csv(args.out_dir / "unmatched_pokemon_names.csv", index=False)
    print(coverage(mapping, unmatched))
    print(f"Top unmatched (write fixes into {args.overrides}):")
    print(unmatched.head(15).to_string(index=False))
    if args.to_mysql:
        write_mapping_table(mapping, engine)
        print(f"Wrote {len(mapping)} rows to {MAP_TABLE}")


if __name__ == "__main__":
    main()