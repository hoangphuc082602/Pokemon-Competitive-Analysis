"""Crawl PokéAPI abilities -> data/raw/ability_raw.csv (ability_id, ability_name, effect = English short effect).

    python -m python.crawl_data.data_ability                       # every id listed by /ability
    python -m python.crawl_data.data_ability --ids 22 312          # small test range (add --to-mysql to load MySQL)

Ids come from the /ability list, so abilities added to PokéAPI later (e.g. 312-314, used by new Mega forms in
pokemon_ability.csv) are crawled too (#44). An ability with no English effect keeps its row with an empty effect.
Resumable, retried with backoff, rate-limited; failures in ability_raw_failures.csv, crawled ids in
ability_raw_progress.csv: see python/crawl_data/pokeapi_crawl.py. Nothing runs on import; with --to-mysql the MySQL
table ability is rebuilt from the full CSV (if_exists="replace").
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd
import requests

from python.crawl_data.pokeapi_crawl import API_URL, crawl_rows, fetch_json, list_ids

ABILITY_URL = f"{API_URL}ability/"
COLUMNS = ["ability_id", "ability_name", "effect"]


def extract_ability(data: dict) -> list[dict]:
    """The row of one /ability response; effect is None when there is no English short effect."""
    effect = next((e.get("short_effect") for e in data.get("effect_entries") or []
                   if e["language"]["name"] == "en"), None)
    return [{"ability_id": int(data["id"]), "ability_name": str(data["name"]), "effect": effect}]


def crawl_abilities(ids: Iterable[int], fetch: Callable[[int], dict], out_csv: Path, failures_csv: Path,
                    progress_csv: Path, delay: float = 0.2) -> dict[str, int]:
    """Fetch every ability id not yet crawled, appending its row; returns counts of this run."""
    return crawl_rows(ids, fetch, extract_ability, COLUMNS, out_csv, failures_csv, progress_csv, delay,
                      id_column="ability_id")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", type=int, nargs="+", help="crawl only these /ability ids (default: all)")
    ap.add_argument("--out", type=Path, default=Path("data/raw/ability_raw.csv"))
    ap.add_argument("--delay", type=float, default=0.2, help="seconds between requests")
    ap.add_argument("--retries", type=int, default=4, help="retries of a 429 / 5xx / timeout, with backoff")
    ap.add_argument("--to-mysql", action="store_true", help="rebuild the MySQL table ability from the CSV")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    out = args.out
    failures, progress = (out.with_name(f"{out.stem}_{s}.csv") for s in ("failures", "progress"))

    session = requests.Session()
    ids = args.ids or list_ids(session, ABILITY_URL, args.retries)
    counts = crawl_abilities(ids, lambda aid: fetch_json(session, f"{ABILITY_URL}{aid}/", retries=args.retries),
                             out, failures, progress, args.delay)
    df = pd.read_csv(out)
    print(f"this run: {counts}")
    print(f"{out}: {len(df)} abilities (ids {df['ability_id'].min()}..{df['ability_id'].max()}), "
          f"{df['effect'].isna().sum()} without an English effect; failures this run: {counts['failed']} "
          f"-> {failures}")
    if args.to_mysql:
        from python.database.db_connection import engine
        df.to_sql(name="ability", con=engine, if_exists="replace", index=False)
        print(f"MySQL ability replaced: {len(df)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
