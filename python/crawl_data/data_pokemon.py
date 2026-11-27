"""Crawl PokéAPI typing per /pokemon entry -> data/raw/pokemon_type_raw.csv (pokemon_id, type_id, slot).

    python -m python.crawl_data.data_pokemon                       # every /pokemon entry, incl. alternate forms (ids >= 10001)
    python -m python.crawl_data.data_pokemon --ids 892 10191      # small test range (add --to-mysql to load MySQL)

pokemon_id is the PokéAPI /pokemon id (= poke_id of pokemon_stats / pokemon_usage_stats), so alternate forms
(e.g. urshifu-rapid-strike = 10191) get their own typing (#25). Resumable, retried with backoff (429 / 5xx /
timeouts, --retries), rate-limited (--delay), crawled ids in pokemon_type_raw_progress.csv: see
python/crawl_data/pokeapi_crawl.py (#44). Failures (HTTP error after retries, no types) are logged and written to
pokemon_type_failures.csv (this run's failures only; a rerun retries them).
With --to-mysql the MySQL table pokemon_types is rebuilt from the full CSV at the end (if_exists="replace"); it then
also holds alternate forms, which python/database/pokemon_loader.py LEFT JOINs from pokemon_stats on poke_id.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd
import requests

from python.crawl_data.pokeapi_crawl import (ALTERNATE_FORM_MIN_ID, POKEMON_URL, all_pokemon_ids,
                                             crawl_rows, fetch_json, ref_id)

COLUMNS = ["pokemon_id", "type_id", "slot"]


def extract_types(data: dict) -> list[dict]:
    """Type rows of one /pokemon response, by slot. Raises ValueError when the response has no type."""
    types = sorted(data.get("types") or [], key=lambda t: t["slot"])
    if not types:
        raise ValueError(f"no types in the response for pokemon {data.get('id')}")
    return [{"pokemon_id": int(data["id"]), "type_id": ref_id(t["type"]), "slot": int(t["slot"])} for t in types]


def crawl_types(ids: Iterable[int], fetch: Callable[[int], dict], out_csv: Path, failures_csv: Path,
                delay: float = 0.2) -> dict[str, int]:
    """Fetch the typing of every id not yet crawled, appending its rows; returns counts of this run.
    Crawled ids are recorded in <out>_progress.csv next to `out_csv`."""
    out_csv = Path(out_csv)
    progress_csv = out_csv.with_name(f"{out_csv.stem}_progress.csv")
    crawled = []

    def extract(data: dict) -> list[dict]:
        rows = extract_types(data)
        crawled.append(rows[0]["pokemon_id"])
        return rows

    counts = crawl_rows(ids, fetch, extract, COLUMNS, out_csv, failures_csv, progress_csv, delay)
    alternate = sum(pid >= ALTERNATE_FORM_MIN_ID for pid in crawled)
    return {"already_done": counts["already_done"], "base_forms": len(crawled) - alternate,
            "alternate_forms": alternate, "failed": counts["failed"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", type=int, nargs="+", help="crawl only these /pokemon ids (default: all)")
    ap.add_argument("--out", type=Path, default=Path("data/raw/pokemon_type_raw.csv"))
    ap.add_argument("--failures", type=Path, default=Path("data/raw/pokemon_type_failures.csv"))
    ap.add_argument("--delay", type=float, default=0.2, help="seconds between requests")
    ap.add_argument("--retries", type=int, default=4, help="retries of a 429 / 5xx / timeout, with backoff")
    ap.add_argument("--to-mysql", action="store_true", help="rebuild the MySQL table pokemon_types from the CSV")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    session = requests.Session()
    ids = args.ids or all_pokemon_ids(session, retries=args.retries)
    counts = crawl_types(ids, lambda pid: fetch_json(session, f"{POKEMON_URL}{pid}/", retries=args.retries),
                         args.out, args.failures, args.delay)
    df = pd.read_csv(args.out)
    print(f"this run: {counts}")
    print(f"{args.out}: {df['pokemon_id'].nunique()} pokemon "
          f"({df.loc[df['pokemon_id'] < ALTERNATE_FORM_MIN_ID, 'pokemon_id'].nunique()} base forms, "
          f"{df.loc[df['pokemon_id'] >= ALTERNATE_FORM_MIN_ID, 'pokemon_id'].nunique()} alternate forms), "
          f"{len(df)} rows; failures this run: {counts['failed']} -> {args.failures}")
    if args.to_mysql:
        from python.database.db_connection import engine
        df.to_sql(name="pokemon_types", con=engine, if_exists="replace", index=False)
        print(f"MySQL pokemon_types replaced: {len(df)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
