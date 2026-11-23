"""Crawl PokéAPI typing per /pokemon entry -> data/raw/pokemon_type_raw.csv (pokemon_id, type_id, slot).

    python -m python.crawl_data.data_pokemon                       # every /pokemon entry, incl. alternate forms (ids >= 10001)
    python -m python.crawl_data.data_pokemon --ids 892 10191 --no-sql   # small test range

pokemon_id is the PokéAPI /pokemon id (= poke_id of pokemon_stats / pokemon_usage_stats), so alternate forms
(e.g. urshifu-rapid-strike = 10191) get their own typing (#25). Resumable: ids already in the output CSV are skipped
and each pokemon's rows are appended as soon as they are fetched. Rate-limited (--delay). Failures (HTTP error, no
types) are logged and written to pokemon_type_failures.csv (this run's failures only; a rerun retries them).
With --no-sql the MySQL table pokemon_types is not replaced; otherwise it is rebuilt from the full CSV at the end.
"""
from __future__ import annotations

import argparse
import csv
import logging
import time
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd
import requests

BASE_URL = "https://pokeapi.co/api/v2/pokemon/"
ALTERNATE_FORM_MIN_ID = 10001
COLUMNS = ["pokemon_id", "type_id", "slot"]
log = logging.getLogger(__name__)


def extract_types(data: dict) -> list[dict]:
    """Type rows of one /pokemon response, by slot. Raises ValueError when the response has no type."""
    types = sorted(data.get("types") or [], key=lambda t: t["slot"])
    if not types:
        raise ValueError(f"no types in the response for pokemon {data.get('id')}")
    return [{"pokemon_id": int(data["id"]), "type_id": int(t["type"]["url"].rstrip("/").split("/")[-1]),
             "slot": int(t["slot"])} for t in types]


def _done_ids(out_csv: Path) -> set[int]:
    if not out_csv.exists() or out_csv.stat().st_size == 0:
        return set()
    return set(pd.read_csv(out_csv, usecols=["pokemon_id"])["pokemon_id"].astype(int))


def crawl_types(ids: Iterable[int], fetch: Callable[[int], dict], out_csv: Path, failures_csv: Path,
                delay: float = 0.2) -> dict[str, int]:
    """Fetch the typing of every id not yet in `out_csv`, appending its rows; returns counts of this run."""
    out_csv, failures_csv = Path(out_csv), Path(failures_csv)
    done = _done_ids(out_csv)
    counts = {"already_done": 0, "base_forms": 0, "alternate_forms": 0, "failed": 0}
    failures = []
    new_file = not out_csv.exists() or out_csv.stat().st_size == 0
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        if new_file:
            writer.writeheader()
        for i, pid in enumerate(ids):
            if pid in done:
                counts["already_done"] += 1
                continue
            if i and delay:
                time.sleep(delay)
            try:
                rows = extract_types(fetch(pid))
            except (requests.RequestException, ValueError, KeyError, RuntimeError) as e:
                log.warning("pokemon %s failed: %s", pid, e)
                failures.append({"pokemon_id": pid, "error": str(e)})
                counts["failed"] += 1
                continue
            writer.writerows(rows)
            fh.flush()
            done.add(pid)
            counts["alternate_forms" if pid >= ALTERNATE_FORM_MIN_ID else "base_forms"] += 1
    pd.DataFrame(failures, columns=["pokemon_id", "error"]).to_csv(failures_csv, index=False)
    return counts


def all_pokemon_ids(session: requests.Session) -> list[int]:
    """Every /pokemon id (base forms 1..1025 and alternate forms >= 10001)."""
    res = session.get(f"{BASE_URL}?limit=100000", timeout=30)
    res.raise_for_status()
    return sorted(int(p["url"].rstrip("/").split("/")[-1]) for p in res.json()["results"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", type=int, nargs="+", help="crawl only these /pokemon ids (default: all)")
    ap.add_argument("--out", type=Path, default=Path("data/raw/pokemon_type_raw.csv"))
    ap.add_argument("--failures", type=Path, default=Path("data/raw/pokemon_type_failures.csv"))
    ap.add_argument("--delay", type=float, default=0.2, help="seconds between requests")
    ap.add_argument("--no-sql", action="store_true", help="do not rebuild the MySQL table pokemon_types")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    session = requests.Session()

    def fetch(pid: int) -> dict:
        res = session.get(f"{BASE_URL}{pid}/", timeout=30)
        res.raise_for_status()
        return res.json()

    ids = args.ids or all_pokemon_ids(session)
    counts = crawl_types(ids, fetch, args.out, args.failures, args.delay)
    df = pd.read_csv(args.out)
    print(f"this run: {counts}")
    print(f"{args.out}: {df['pokemon_id'].nunique()} pokemon "
          f"({df.loc[df['pokemon_id'] < ALTERNATE_FORM_MIN_ID, 'pokemon_id'].nunique()} base forms, "
          f"{df.loc[df['pokemon_id'] >= ALTERNATE_FORM_MIN_ID, 'pokemon_id'].nunique()} alternate forms), "
          f"{len(df)} rows; failures this run: {counts['failed']} -> {args.failures}")
    if not args.no_sql:
        from python.database.db_connection import engine
        df.to_sql(name="pokemon_types", con=engine, if_exists="replace", index=False)
        print(f"MySQL pokemon_types replaced: {len(df)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
