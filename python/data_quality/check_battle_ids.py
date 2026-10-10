"""Do distinct Showdown replays collapse into one battle_id when it is a hash of the first 500 log characters?

    python -m python.data_quality.check_battle_ids                      # every file in data/vgc_data
    python -m python.data_quality.check_battle_ids --file "data/vgc_data/Gen 9 VGC 2024_part4.parquet"

Per file: log rows, distinct replay ids, distinct hash-based battle_ids, and how many replays the
log-hash scheme would drop (rows whose hash was already seen). Reads only the id and log columns.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pyarrow.parquet as pq

from parser.parser import _generate_battle_id


def check_file(path: Path, id_col: str = "id", log_col: str = "log") -> dict:
    ids, hashes, rows = set(), set(), 0
    for batch in pq.ParquetFile(path).iter_batches(columns=[id_col, log_col], batch_size=2000):
        for rid, log in zip(batch.column(0).to_pylist(), batch.column(1).to_pylist()):
            if not isinstance(log, str) or not log.strip():
                continue
            rows += 1
            ids.add(rid)
            hashes.add(_generate_battle_id(log, "x"))
    return {"file": path.name, "rows": rows, "distinct_ids": len(ids), "distinct_hashes": len(hashes),
            "dropped_by_hash": rows - len(hashes), "duplicate_ids": rows - len(ids)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=Path("data/vgc_data"))
    ap.add_argument("--file", type=Path, default=None)
    args = ap.parse_args(argv)
    files = [args.file] if args.file else sorted(args.data_dir.glob("*.parquet"))
    print(f"{'file':<34}{'rows':>9}{'ids':>9}{'hashes':>9}{'dropped':>9}{'dup ids':>9}")
    total = {"rows": 0, "distinct_ids": 0, "distinct_hashes": 0, "dropped_by_hash": 0, "duplicate_ids": 0}
    for f in files:
        r = check_file(f)
        print(f"{r['file']:<34}{r['rows']:>9,}{r['distinct_ids']:>9,}{r['distinct_hashes']:>9,}"
              f"{r['dropped_by_hash']:>9,}{r['duplicate_ids']:>9,}")
        for k in total:
            total[k] += r[k]
    print(f"{'TOTAL (per-file, not cross-file)':<34}{total['rows']:>9,}{total['distinct_ids']:>9,}"
          f"{total['distinct_hashes']:>9,}{total['dropped_by_hash']:>9,}{total['duplicate_ids']:>9,}")
    print("\ndropped = rows whose hash-based battle_id already existed in the same file (silently skipped by runner.py).")
    print("dup ids = rows sharing a replay id (true duplicates in the crawl).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())