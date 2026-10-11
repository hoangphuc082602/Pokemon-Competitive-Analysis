"""Check what |switch| details really contain for species whose form is masked at team preview.

    python -m python.data_quality.probe_switch_details --file "data/vgc_data/Gen 9 VGC 2024_part4.parquet" --species urshifu

Prints the distinct details strings seen in |switch|/|drag| lines and the |poke| strings for that species.
If switch details show 'Urshifu-Rapid-Strike' (not 'Urshifu-*'), parser v2 can recover the form.
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", type=Path, required=True)
    ap.add_argument("--species", required=True, help="case-insensitive text, e.g. urshifu")
    ap.add_argument("--log-col", default="log")
    ap.add_argument("--limit", type=int, default=5000, help="logs to scan")
    args = ap.parse_args(argv)

    needle = args.species.lower()
    switch_re = re.compile(r"^\|(?:switch|drag|detailschange|replace)\|[^|]*\|([^|]+)", re.M)
    poke_re = re.compile(r"^\|poke\|p[12]\|([^|]+)", re.M)
    switches, pokes, scanned = Counter(), Counter(), 0
    for batch in pq.ParquetFile(args.file).iter_batches(columns=[args.log_col], batch_size=500):
        for log in batch.column(0).to_pylist():
            scanned += 1
            for m in switch_re.finditer(log or ""):
                if needle in m.group(1).lower():
                    switches[m.group(1).strip()] += 1
            for m in poke_re.finditer(log or ""):
                if needle in m.group(1).lower():
                    pokes[m.group(1).strip()] += 1
            if scanned >= args.limit:
                break
        if scanned >= args.limit:
            break
    print(f"scanned {scanned:,} logs")
    print("\n|poke| details:");   print("\n".join(f"  {n:>7,}  {d}" for d, n in pokes.most_common(8)) or "  (none)")
    print("\n|switch| details:"); print("\n".join(f"  {n:>7,}  {d}" for d, n in switches.most_common(12)) or "  (none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())