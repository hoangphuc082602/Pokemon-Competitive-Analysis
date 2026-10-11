"""Map Pokémon Showdown names (battle_*.pokemon_name) to PokéAPI master rows (pokemon_stats).

Matching is deliberately conservative:
  1. explicit override  (python/data_quality/showdown_overrides.csv)
  2. exact match after normalisation  ("Flutter Mane" -> "flutter-mane")
  4. form missing from the master data ("Arceus-Fire", "Ogerpon-Wellspring-Tera") -> species only,
     form_status = 'unlisted'. Forms are never merged: their stats / types / abilities may differ.
  3. masked team-preview name  ("Urshifu-*")  -> species only: the form is hidden by Showdown and is NOT
     recoverable from the event tables, so poke_id stays NULL and form_status = 'masked'
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
DEFAULT_NON_CANONICAL = Path(__file__).with_name("showdown_non_canonical.csv")   # fan-made (CAP) names, not in PokeAPI
MAP_TABLE = "showdown_pokemon_map"
MASK_SUFFIX = "-*"   # Showdown hides the form of some species at team preview, e.g. "Urshifu-*"


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


def load_non_canonical(path: Path = DEFAULT_NON_CANONICAL) -> set[str]:
    """CSV with column showdown_name: fake Pokemon (CAP) that must not pollute the mapping and its reports."""
    return set(pd.read_csv(path, dtype=str).dropna()["showdown_name"].str.strip()) if path.exists() else set()


def drop_non_canonical(counts: Counter, fake: set[str]) -> tuple[Counter, Counter]:
    """Split name counts into (canonical, ignored)."""
    return (Counter({n: c for n, c in counts.items() if n not in fake}),
            Counter({n: c for n, c in counts.items() if n in fake}))



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
    return pd.read_sql("SELECT poke_id, pokemon, species_id FROM pokemon_stats", engine)


# ---------------------------------------------------------------- core
def build_mapping(counts: Counter, master: pd.DataFrame, overrides: dict[str, str] | None = None):
    """Return (mapping, unmatched). `counts` = {showdown_name: number_of_rows}.

    mapping   : showdown_name, poke_id, pokemon, species_id, method ('override' | 'exact' | 'masked' | 'unlisted'),
                form_status ('known' | 'masked' | 'unlisted'), n_rows.  Masked rows have NULL poke_id / pokemon.
    unmatched : showdown_name, n_rows, suggestions   (sorted by n_rows, biggest first)
    """
    overrides = overrides or {}
    has_species = "species_id" in master.columns
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
        species_id, status = None, "masked"
        if slug is None and has_species:
            species_id = _masked_species_id(name, slug_to_row)
            if species_id is None:           # form missing from the master data: species only, never a guessed form
                species_id, status = _family_species_id(name, slug_to_row), "unlisted"
        if slug is None and species_id is None:
            unmatched.append({"showdown_name": name, "n_rows": n_rows,
                              "suggestions": "; ".join(_suggest(name, slug_to_row))})
        elif slug is None:
            mapped.append({"showdown_name": name, "poke_id": None, "pokemon": None, "species_id": species_id,
                           "method": status, "form_status": status, "n_rows": n_rows})
        else:
            r = slug_to_row[slug]
            sid = getattr(r, "species_id", None)
            mapped.append({"showdown_name": name, "poke_id": int(r.poke_id), "pokemon": r.pokemon,
                           "species_id": int(sid) if sid is not None and pd.notna(sid) else None,
                           "method": method, "form_status": "known", "n_rows": n_rows})

    mapping = pd.DataFrame(mapped, columns=["showdown_name", "poke_id", "pokemon", "species_id", "method",
                                            "form_status", "n_rows"])
    mapping = mapping.astype({"poke_id": "Int64", "species_id": "Int64"})
    report = pd.DataFrame(unmatched, columns=["showdown_name", "n_rows", "suggestions"])
    return mapping, report.sort_values("n_rows", ascending=False, ignore_index=True)


def _masked_species_id(name: str, slug_to_row: dict) -> int | None:
    """'Urshifu-*' -> species_id of Urshifu, only if every master form of that species family agrees."""
    if not name.endswith(MASK_SUFFIX):
        return None
    base = normalize_name(name[: -len(MASK_SUFFIX)])
    ids = {int(r.species_id) for slug, r in slug_to_row.items()
           if (slug == base or slug.startswith(base + "-")) and pd.notna(r.species_id)}
    return ids.pop() if len(ids) == 1 else None


def _family_species_id(name: str, slug_to_row: dict) -> int | None:
    """'Arceus-Fire' / 'Ogerpon-Wellspring-Tera' -> species_id of the family, only for form-like names
    (with a hyphen suffix) not present in the master data and only if the whole family is one species."""
    slug = normalize_name(name)
    if "-" not in slug:
        return None
    base = slug.split("-")[0]
    ids = {int(r.species_id) for s, r in slug_to_row.items()
           if (s == base or s.startswith(base + "-")) and pd.notna(r.species_id)}
    return ids.pop() if len(ids) == 1 else None


def _suggest(name: str, slug_to_row: dict, limit: int = 3) -> list[str]:
    slug = normalize_name(name)
    base = slug.split("-")[0]
    prefixed = sorted(s for s in slug_to_row if s.startswith(slug + "-"))      # 'mimikyu' -> 'mimikyu-...'
    fuzzy = difflib.get_close_matches(slug, slug_to_row, n=limit, cutoff=0.6)
    same_base = sorted(s for s in slug_to_row if s == base or s.startswith(base + "-"))
    return list(dict.fromkeys(prefixed + fuzzy + same_base))[:limit]


def coverage(mapping: pd.DataFrame, unmatched: pd.DataFrame) -> dict:
    """Coverage weighted by rows (the denominator that matters for usage / win-rate stats) and by distinct names."""
    species_only = ["masked", "unlisted"]    # species known, exact form not
    is_masked = mapping["form_status"].isin(species_only) if "form_status" in mapping else pd.Series(False, index=mapping.index)
    rows_masked, names_masked = int(mapping.loc[is_masked, "n_rows"].sum()), int(is_masked.sum())
    rows_ok, rows_bad = int(mapping["n_rows"].sum()) - rows_masked, int(unmatched["n_rows"].sum())
    names_ok, names_bad = len(mapping) - names_masked, len(unmatched)
    rows_total, names_total = rows_ok + rows_masked + rows_bad, names_ok + names_masked + names_bad
    return {
        "rows_total": rows_total,
        "rows_matched_pct": round(100 * rows_ok / max(rows_total, 1), 3),            # exact form known
        "rows_species_only_pct": round(100 * rows_masked / max(rows_total, 1), 3),   # masked form, species known
        "names_total": names_total,
        "names_matched_pct": round(100 * names_ok / max(names_total, 1), 3),
        "names_species_only": names_masked,
    }


def write_mapping_table(mapping: pd.DataFrame, engine, table: str = MAP_TABLE) -> None:
    """Replace the lookup table (small: one row per distinct Showdown name)."""
    from sqlalchemy import BigInteger, String

    mapping[["showdown_name", "poke_id", "pokemon", "species_id", "method", "form_status"]].to_sql(
        table, engine, if_exists="replace", index=False,
        dtype={"showdown_name": String(100), "pokemon": String(100), "method": String(10),
               "form_status": String(10), "poke_id": BigInteger(), "species_id": BigInteger()},
    )


# ---------------------------------------------------------------- CLI
def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--team-slot", type=Path, default=Path("data/output/battle_team_slot.parquet"))
    ap.add_argument("--column", default="pokemon_name")
    ap.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    ap.add_argument("--out-dir", type=Path, default=Path("data/mapping"))
    ap.add_argument("--to-mysql", action="store_true", help=f"also (re)write table {MAP_TABLE}")
    ap.add_argument("--species-dir", type=Path, default=None,
                    help="also count the real species names (battle_leads / battle_switch 'species') in this output dir")
    args = ap.parse_args(argv)

    from python.database.db_connection import engine

    counts = count_names_from_parquet(args.team_slot, args.column)
    if args.species_dir:
        for table in ("battle_leads", "battle_switch"):
            counts += count_names_from_parquet(args.species_dir / f"{table}.parquet", "species")
    counts, ignored = drop_non_canonical(counts, load_non_canonical())
    if ignored:
        print(f"Ignored {len(ignored)} non-canonical (CAP) names, {sum(ignored.values()):,} rows: {sorted(ignored)}")
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