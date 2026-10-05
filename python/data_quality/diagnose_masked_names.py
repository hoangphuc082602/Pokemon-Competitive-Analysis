"""One-off diagnostic: can masked team-preview names (e.g. 'Urshifu-*') be resolved from the log itself?

For every parquet in data/vgc_data it scans logs and reports, per file:
  logs scanned | logs with |showteam| | logs with a masked |poke| name
  masked slots resolvable from |showteam|      (showteam has an entry whose species starts with the base name)
  masked slots resolvable from battle events   (|switch|/|drag|/|detailschange| shows the real forme for that side)
  masked slots NOT resolvable by either        (e.g. the Pokemon was never sent out and there is no showteam)
and prints a couple of raw examples.

Run from the repo root:   python diagnose_masked_names.py [--limit 50000]
Safe: read-only, prints public replay text only.
"""
import argparse
import re
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

MASKED = re.compile(r"\|poke\|(p[12])\|([^,|]+?)-\*")
SHOWTEAM = re.compile(r"^\|showteam\|(p[12])\|(.*)$", re.M)
EVENT = re.compile(r"\|(?:switch|drag|detailschange|-formechange)\|(p[12])[ab]: [^|]*\|([^,|]+)")


def showteam_species(line_body: str) -> list[str]:
    """Packed team format: mons separated by ']', fields by '|' -> NICKNAME|SPECIES|ITEM|...  (species blank = nickname)."""
    out = []
    for mon in line_body.split("]"):
        f = mon.split("|")
        out.append((f[1] if len(f) > 1 and f[1] else f[0]).strip())
    return out


def analyse(log: str):
    masked = MASKED.findall(log)
    if not masked:
        return None
    teams = {side: showteam_species(body) for side, body in SHOWTEAM.findall(log)}
    seen = {(side, sp) for side, sp in EVENT.findall(log)}
    rows = []
    for side, base in masked:
        by_team = [s for s in teams.get(side, []) if s == base or s.startswith(base + "-")]
        by_events = sorted({sp for sd, sp in seen if sd == side and (sp == base or sp.startswith(base + "-"))})
        rows.append((side, base, by_team, by_events))
    return rows, bool(teams)


def main(limit: int):
    for path in sorted(Path("data/vgc_data").glob("*.parquet")):
        pf = pq.ParquetFile(path)
        col = "log" if "log" in pf.schema_arrow.names else pf.schema_arrow.names[0]
        stats, examples, scanned = Counter(), [], 0
        for batch in pf.iter_batches(columns=[col], batch_size=2000):
            for log in batch.column(0).to_pylist():
                if scanned >= limit:
                    break
                scanned += 1
                log = log or ""
                has_team = "|showteam|" in log
                stats["with_showteam"] += has_team
                res = analyse(log)
                if not res:
                    continue
                rows, _ = res
                stats["logs_with_masked"] += 1
                for side, base, by_team, by_events in rows:
                    stats["masked_slots"] += 1
                    stats["by_showteam"] += bool(by_team)
                    stats["by_events"] += bool(by_events)
                    stats["unresolved"] += not (by_team or by_events)
                    stats[f"base:{base}"] += 1
                    if len(examples) < 2 and (by_team or by_events):
                        examples.append((side, base, by_team, by_events))
        print(f"\n== {path.name}")
        print(f"   scanned {scanned:,} | with |showteam| {stats['with_showteam']:,} | logs with masked name {stats['logs_with_masked']:,}")
        if stats["masked_slots"]:
            n = stats["masked_slots"]
            print(f"   masked slots {n:,}: from showteam {stats['by_showteam']:,} ({100*stats['by_showteam']/n:.1f}%) | "
                  f"from events {stats['by_events']:,} ({100*stats['by_events']/n:.1f}%) | unresolved {stats['unresolved']:,} ({100*stats['unresolved']/n:.1f}%)")
            print("   bases:", {k[5:]: v for k, v in stats.items() if k.startswith("base:")})
            for ex in examples:
                print("   example (side, masked base, showteam match, event match):", ex)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50_000, help="max logs scanned per file")
    main(ap.parse_args().limit)