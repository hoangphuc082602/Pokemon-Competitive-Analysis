"""Resumable per-/pokemon crawl shared by the learnset and ability crawls (#36).

crawl_rows fetches every id not yet crawled, appends its rows to the output CSV and records the id in a progress CSV
(pokemon_id, rows) even when it has no rows (e.g. a Mega form has no Scarlet / Violet learnset), so a rerun does not
fetch it again. Ids already in an output CSV written before the progress file existed also count as crawled.
Failures (HTTP error after retries, malformed payload) go to the failures CSV (this run's failures only; a rerun
retries them).
"""
from __future__ import annotations

import csv
import logging
import time
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd
import requests

log = logging.getLogger(__name__)
RETRY_STATUS = (429, 500, 502, 503, 504)


def fetch_json(session, url: str, retries: int = 4, backoff: float = 1.0,
               sleep: Callable[[float], None] = time.sleep) -> dict:
    """GET `url` as JSON. Rate limits, server errors, timeouts and connection errors are retried `retries` times,
    waiting backoff, 2*backoff, 4*backoff...; any other HTTP error (e.g. 404) is raised at once."""
    for attempt in range(retries + 1):
        try:
            res = session.get(url, timeout=30)
            res.raise_for_status()
            return res.json()
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as e:
            transient = not isinstance(e, requests.HTTPError) or res.status_code in RETRY_STATUS
            if not transient or attempt == retries:
                raise
            wait = backoff * 2 ** attempt
            log.info("%s: %s, retry in %.1fs", url, e, wait)
            sleep(wait)
    raise AssertionError("unreachable")


def _ids_in(path: Path) -> set[int]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    return set(pd.read_csv(path, usecols=["pokemon_id"])["pokemon_id"].astype("int64").tolist())


def _appender(path: Path, columns: list[str]):
    new_file = not path.exists() or path.stat().st_size == 0
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = path.open("a", newline="", encoding="utf-8")
    writer = csv.DictWriter(fh, fieldnames=columns)
    if new_file:
        writer.writeheader()
    return fh, writer


def crawl_rows(ids: Iterable[int], fetch: Callable[[int], dict], extract: Callable[[dict], list[dict]],
               columns: list[str], out_csv: Path, failures_csv: Path, progress_csv: Path,
               delay: float = 0.2) -> dict[str, int]:
    """Crawl every id not yet done (see the module docstring); returns counts of this run."""
    out_csv, failures_csv, progress_csv = Path(out_csv), Path(failures_csv), Path(progress_csv)
    done = _ids_in(out_csv) | _ids_in(progress_csv)
    counts = {"already_done": 0, "crawled": 0, "empty": 0, "failed": 0}
    failures = []
    out_fh, out = _appender(out_csv, columns)
    prog_fh, prog = _appender(progress_csv, ["pokemon_id", "rows"])
    try:
        fetched = 0
        for pid in ids:
            if pid in done:
                counts["already_done"] += 1
                continue
            if fetched and delay:
                time.sleep(delay)
            fetched += 1
            try:
                rows = extract(fetch(pid))
            except (requests.RequestException, ValueError, KeyError, TypeError) as e:
                log.warning("pokemon %s failed: %s", pid, e)
                failures.append({"pokemon_id": pid, "error": str(e)})
                counts["failed"] += 1
                continue
            out.writerows(rows)
            out_fh.flush()
            prog.writerow({"pokemon_id": pid, "rows": len(rows)})
            prog_fh.flush()
            done.add(pid)
            counts["crawled"] += 1
            counts["empty"] += not rows
    finally:
        out_fh.close()
        prog_fh.close()
    pd.DataFrame(failures, columns=["pokemon_id", "error"]).to_csv(failures_csv, index=False)
    return counts


def run_cli(argv, description: str, extract: Callable[[dict], list[dict]], columns: list[str],
            default_out: Path, table: str) -> int:
    """Command line shared by the per-/pokemon crawls: --ids (default: every /pokemon id, alternate forms included),
    --out (failures / progress CSVs sit next to it), --delay, --retries, --to-mysql (rebuild `table` from the CSV)."""
    import argparse

    from python.crawl_data.data_pokemon import ALTERNATE_FORM_MIN_ID, all_pokemon_ids

    ap = argparse.ArgumentParser(description=description, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", type=int, nargs="+", help="crawl only these /pokemon ids (default: all)")
    ap.add_argument("--out", type=Path, default=default_out)
    ap.add_argument("--delay", type=float, default=0.2, help="seconds between pokemon")
    ap.add_argument("--retries", type=int, default=4, help="retries of a 429 / 5xx / timeout, with backoff")
    ap.add_argument("--to-mysql", action="store_true", help=f"rebuild the MySQL table {table} from the CSV")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    out = args.out
    failures, progress = (out.with_name(f"{out.stem}_{s}.csv") for s in ("failures", "progress"))

    session = requests.Session()
    ids = args.ids or all_pokemon_ids(session)
    counts = crawl_rows(ids, lambda pid: fetch_json(session, f"https://pokeapi.co/api/v2/pokemon/{pid}/",
                                                    retries=args.retries),
                        extract, columns, out, failures, progress, args.delay)
    df = pd.read_csv(out)
    prog = pd.read_csv(progress)
    alt = prog["pokemon_id"] >= ALTERNATE_FORM_MIN_ID
    print(f"this run: {counts}")
    print(f"{out}: {len(df)} rows; crawled {len(prog)} pokemon ({(~alt).sum()} base forms, {alt.sum()} alternate "
          f"forms), {(prog['rows'] == 0).sum()} with no rows -> {progress}; failures this run: {counts['failed']} "
          f"-> {failures}")
    if args.to_mysql:
        from python.database.db_connection import engine
        df.to_sql(name=table, con=engine, if_exists="replace", index=False)
        print(f"MySQL {table} replaced: {len(df)} rows")
    return 0
