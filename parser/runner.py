"""
runner.py  –  Production runner for Pokemon Showdown VGC parquet logs
======================================================================

Reads parquet files from  data/vgc_data/*.parquet,
parses each log string through the state-machine parser,
and writes one parquet file per table into  output/<table_name>.parquet.

Dependencies
------------
    pip install pyarrow pandas

Usage
-----
    python runner.py                        # default: data/vgc_data/*.parquet
    python runner.py --data-dir ./my/path   # custom input directory
    python runner.py --out-dir  ./results   # custom output directory
    python runner.py --batch    1000         # rows-per-flush (RAM control)
    python runner.py --log-col  "log"       # parquet column containing the log text
    python runner.py --workers  4           # parallel workers (0 = serial)
    python runner.py --dry-run              # parse without writing output
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Optional

import pandas as pd

# ── parser must live next to this file (or be on PYTHONPATH) ──────────────────
try:
    # imported as a package (tests, `python -m parser.runner`)
    from parser.parser import BatchParser, InMemoryDB, _generate_battle_id, BattleLogParser
except ImportError:
    try:
        # run as a script (`python parser/runner.py`): `parser` is the sibling parser.py
        from parser import BatchParser, InMemoryDB, _generate_battle_id, BattleLogParser
    except ImportError as exc:
        sys.exit(
            f"[FATAL] Cannot import parser.py – make sure it is in the same directory.\n{exc}"
        )

# ── optional pyarrow (graceful degradation to CSV if absent) ─────────────────
try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    HAS_PYARROW = True
except ImportError:
    HAS_PYARROW = False


# =============================================================================
# Logging setup
# =============================================================================

LOG_FORMAT = "%(asctime)s  %(levelname)-7s  %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt="%H:%M:%S")
log = logging.getLogger("runner")


# =============================================================================
# Schema column order (mirrors DDL – controls output column order)
# =============================================================================

TABLE_COLUMNS: dict[str, list[str]] = {
    "battle": [
        "battle_id", "format", "format_id", "upload_time", "rating",
        "winner_name", "replay_path", "turn_count",
    ],
    "players": ["username"],
    "battle_players": [
        "battle_id", "username", "side",
        "rating_before", "rating_after", "result",
    ],
    "battle_team_slot": [
        "battle_id", "player_side", "slot_no", "pokemon_name", "is_lead",
    ],
    "battle_leads": [
        "battle_id", "username", "pokemon_name", "lead_slot",
    ],
    "battle_move": [
        "battle_id", "turn_no", "username", "pokemon_name",
        "move_name", "target_name", "success",
    ],
    "battle_damage": [
        "battle_id", "turn_no", "attacker_pokemon", "defender_pokemon",
        "move_name", "hp_before", "hp_after", "damage_pct",
    ],
    "battle_ko": [
        "battle_id", "turn_no", "killer_pokemon", "victim_pokemon",
        "move_name", "ko_type",
    ],
    "battle_faint": ["battle_id", "turn_no", "pokemon_name"],
    "battle_switch": ["battle_id", "turn_no", "username", "pokemon_name"],
    "battle_weather": ["battle_id", "turn_no", "weather_name", "source_pokemon"],
    "battle_status": ["battle_id", "turn_no", "pokemon_name", "status_code"],
    "battle_ability": ["battle_id", "turn_no", "pokemon_name", "ability_name"],
    "battle_tera": ["battle_id", "turn_no", "pokemon_name", "tera_type"],
    "battle_field_state": [
        "battle_id", "turn_no",
        "p1_left", "p1_right", "p2_left", "p2_right",
    ],
}

# Pandas dtypes used when building DataFrames (improves storage efficiency)
TABLE_DTYPES: dict[str, dict[str, str]] = {
    "battle": {
        "battle_id": "string", "format": "string", "format_id": "string",
        "upload_time": "Int64", "rating": "Int32",
        "winner_name": "string", "replay_path": "string",
        "turn_count": "Int32",
    },
    "players": {"username": "string"},
    "battle_players": {
        "battle_id": "string", "username": "string", "side": "string",
        "rating_before": "Int32", "rating_after": "Int32", "result": "string",
    },
    "battle_team_slot": {
        "battle_id": "string", "player_side": "string",
        "slot_no": "Int16", "pokemon_name": "string", "is_lead": "Int8",
    },
    "battle_leads": {
        "battle_id": "string", "username": "string",
        "pokemon_name": "string", "lead_slot": "Int8",
    },
    "battle_move": {
        "battle_id": "string", "turn_no": "Int16", "username": "string",
        "pokemon_name": "string", "move_name": "string",
        "target_name": "string", "success": "Int8",
    },
    "battle_damage": {
        "battle_id": "string", "turn_no": "Int16",
        "attacker_pokemon": "string", "defender_pokemon": "string",
        "move_name": "string",
        "hp_before": "float32", "hp_after": "float32", "damage_pct": "float32",
    },
    "battle_ko": {
        "battle_id": "string", "turn_no": "Int16",
        "killer_pokemon": "string", "victim_pokemon": "string",
        "move_name": "string", "ko_type": "string",
    },
    "battle_faint": {
        "battle_id": "string", "turn_no": "Int16", "pokemon_name": "string",
    },
    "battle_switch": {
        "battle_id": "string", "turn_no": "Int16",
        "username": "string", "pokemon_name": "string",
    },
    "battle_weather": {
        "battle_id": "string", "turn_no": "Int16",
        "weather_name": "string", "source_pokemon": "string",
    },
    "battle_status": {
        "battle_id": "string", "turn_no": "Int16",
        "pokemon_name": "string", "status_code": "string",
    },
    "battle_ability": {
        "battle_id": "string", "turn_no": "Int16",
        "pokemon_name": "string", "ability_name": "string",
    },
    "battle_tera": {
        "battle_id": "string", "turn_no": "Int16",
        "pokemon_name": "string", "tera_type": "string",
    },
    "battle_field_state": {
        "battle_id": "string", "turn_no": "Int16",
        "p1_left": "string", "p1_right": "string",
        "p2_left": "string", "p2_right": "string",
    },
}


# =============================================================================
# Progress tracker
# =============================================================================

@dataclass
class RunStats:
    total_parquet_files: int = 0
    total_log_rows: int = 0
    parsed_ok: int = 0
    parse_errors: int = 0
    skipped_duplicate: int = 0
    start_time: float = dc_field(default_factory=time.time)

    def elapsed(self) -> str:
        s = int(time.time() - self.start_time)
        return f"{s // 60}m{s % 60:02d}s"

    def summary(self) -> str:
        rate = self.parsed_ok / max(1, time.time() - self.start_time)
        return (
            f"Parquet files : {self.total_parquet_files}\n"
            f"Log rows read : {self.total_log_rows}\n"
            f"Parsed OK     : {self.parsed_ok}\n"
            f"Errors        : {self.parse_errors}\n"
            f"Duplicates    : {self.skipped_duplicate}\n"
            f"Elapsed       : {self.elapsed()}\n"
            f"Throughput    : {rate:.1f} battles/s"
        )


# =============================================================================
# Output writers
# =============================================================================

def _rows_to_df(table: str, rows: list[dict]) -> pd.DataFrame:
    """Convert list[dict] → typed DataFrame with DDL column ordering."""
    cols = TABLE_COLUMNS[table]
    dtypes = TABLE_DTYPES.get(table, {})
    # Build with only known columns; fill missing with None
    data = {c: [r.get(c) for r in rows] for c in cols}
    df = pd.DataFrame(data, columns=cols)
    for col, dtype in dtypes.items():
        if col in df.columns:
            try:
                df[col] = df[col].astype(dtype)
            except (ValueError, TypeError):
                pass  # keep as-is if conversion fails
    return df


class ParquetWriter:
    """Incrementally appends DataFrames to per-table parquet files."""

    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        self._writers: dict[str, pq.ParquetWriter] = {}
        self._schemas: dict[str, pa.Schema] = {}

    def write(self, table: str, rows: list[dict]) -> None:
        if not rows:
            return
        df = _rows_to_df(table, rows)
        table_pa = pa.Table.from_pandas(df, preserve_index=False)
        path = self.out_dir / f"{table}.parquet"

        if table not in self._writers:
            self._writers[table] = pq.ParquetWriter(
                str(path), table_pa.schema, compression="snappy"
            )
        self._writers[table].write_table(table_pa)

    def close(self) -> None:
        for w in self._writers.values():
            w.close()
        self._writers.clear()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class CSVWriter:
    """Fallback writer when pyarrow is not available."""

    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        self._handles: dict[str, object] = {}
        self._writers: dict[str, csv.DictWriter] = {}

    def write(self, table: str, rows: list[dict]) -> None:
        if not rows:
            return
        cols = TABLE_COLUMNS[table]
        path = self.out_dir / f"{table}.csv"
        if table not in self._writers:
            fh = open(path, "w", newline="", encoding="utf-8")
            self._handles[table] = fh
            writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            writer.writeheader()
            self._writers[table] = writer
        self._writers[table].writerows(rows)

    def close(self) -> None:
        for fh in self._handles.values():
            fh.close()
        self._handles.clear()
        self._writers.clear()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def make_writer(out_dir: Path) -> "ParquetWriter | CSVWriter":
    if HAS_PYARROW:
        return ParquetWriter(out_dir)
    log.warning("pyarrow not found – falling back to CSV output in %s", out_dir)
    return CSVWriter(out_dir)


# =============================================================================
# Error log (CSV sidecar next to output)
# =============================================================================

class ErrorLog:
    def __init__(self, path: Path):
        self._path = path
        self._fh = open(path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._fh)
        self._writer.writerow(["source_file", "battle_id", "error"])

    def record(self, source_file: str, battle_id: str, error: str) -> None:
        self._writer.writerow([source_file, battle_id, error[:1000]])
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# =============================================================================
# Core parsing helpers
# =============================================================================

def _detect_log_column(df: pd.DataFrame) -> str:
    """
    Auto-detect which column holds the battle log text.
    Prefers columns named 'log', 'replay', 'battle_log', 'text', 'content'.
    Falls back to first string column that looks like a log (contains '|player|').
    """
    candidates = ["log", "replay", "battle_log", "log_text", "text", "content", "data"]
    for name in candidates:
        if name in df.columns:
            return name
    # Inspect dtype
    str_cols = [c for c in df.columns if df[c].dtype == object]
    for col in str_cols:
        sample = df[col].dropna().head(5)
        if sample.str.contains(r"\|player\|", regex=True).any():
            return col
    raise ValueError(
        f"Cannot auto-detect log column. Columns available: {list(df.columns)}. "
        "Use --log-col to specify it explicitly."
    )


def _parse_log_row(
    log_text: str,
    source_file: str,
    row_idx: int,
) -> "tuple[InMemoryDB | None, str, str]":
    """
    Parse one log string.
    Returns (InMemoryDB | None, battle_id, error_msg).
    Designed to be called from a subprocess in parallel mode.
    """
    try:
        battle_id = _generate_battle_id(log_text, source_file + f"#row{row_idx}")
        parser = BattleLogParser(battle_id=battle_id, replay_path=source_file)
        parsed = parser.parse(log_text)
        db = InMemoryDB()
        db.ingest(parsed)
        return db, battle_id, ""
    except Exception:
        err = traceback.format_exc(limit=4)
        return None, "", err


# =============================================================================
# Batch accumulator
# =============================================================================

class TableAccumulator:
    """
    Accumulates rows across InMemoryDB objects and flushes to writer
    once a size threshold is reached.
    """

    def __init__(self, writer, flush_every: int = 5_000):
        self._writer = writer
        self._flush_every = flush_every
        self._buffers: dict[str, list[dict]] = {t: [] for t in TABLE_COLUMNS}
        self._flushed: dict[str, int] = {t: 0 for t in TABLE_COLUMNS}

    def add(self, db: InMemoryDB) -> None:
        for table, rows in db.tables.items():
            if table in self._buffers:
                self._buffers[table].extend(rows)
        # Flush if any buffer exceeds threshold
        if any(len(b) >= self._flush_every for b in self._buffers.values()):
            self.flush()

    def flush(self) -> None:
        for table, rows in self._buffers.items():
            if rows:
                self._writer.write(table, rows)
                self._flushed[table] += len(rows)
                self._buffers[table] = []

    def total_rows(self) -> dict[str, int]:
        return {
            t: self._flushed[t] + len(self._buffers[t])
            for t in TABLE_COLUMNS
        }


# =============================================================================
# Main runner
# =============================================================================

def run(
    data_dir: Path,
    out_dir: Path,
    log_col: Optional[str],
    batch_size: int,
    workers: int,
    dry_run: bool,
) -> RunStats:
    stats = RunStats()

    # ── Discover parquet files ────────────────────────────────────────────────
    parquet_files = list(data_dir.glob("*.parquet"))
    if not parquet_files:
        log.error("No parquet files found in %s", data_dir)
        sys.exit(1)

    stats.total_parquet_files = len(parquet_files)
    log.info("Found %d parquet file(s) in %s", len(parquet_files), data_dir)

    # ── Prepare output ────────────────────────────────────────────────────────
    seen_battle_ids: set[str] = set()
    error_log_path = out_dir / "parse_errors.csv"
    out_dir.mkdir(parents=True, exist_ok=True)

    with make_writer(out_dir) as writer, ErrorLog(error_log_path) as err_log:
        acc = TableAccumulator(writer, flush_every=batch_size)

        for pq_idx, pq_path in enumerate(parquet_files, start=1):
            log.info(
                "[%d/%d] Reading %s",
                pq_idx, len(parquet_files), pq_path.name,
            )
            try:
                df = pd.read_parquet(pq_path)
            except Exception as exc:
                log.error("  Failed to read parquet file: %s", exc)
                stats.parse_errors += 1
                continue

            # Detect log column once per file (column may differ between files)
            col = log_col
            if col is None:
                try:
                    col = _detect_log_column(df)
                    log.info("  Auto-detected log column: '%s'", col)
                except ValueError as exc:
                    log.error("  %s", exc)
                    stats.parse_errors += 1
                    continue

            if col not in df.columns:
                log.error("  Column '%s' not in file. Available: %s", col, list(df.columns))
                stats.parse_errors += 1
                continue

            log_series = df[col].dropna()
            stats.total_log_rows += len(log_series)
            log.info("  %d log rows to parse", len(log_series))

            # ── Serial or parallel ────────────────────────────────────────────
            if workers <= 1 or dry_run:
                _run_serial(
                    log_series=log_series,
                    source_name=str(pq_path),
                    acc=acc,
                    err_log=err_log,
                    stats=stats,
                    seen=seen_battle_ids,
                    dry_run=dry_run,
                )
            else:
                _run_parallel(
                    log_series=log_series,
                    source_name=str(pq_path),
                    acc=acc,
                    err_log=err_log,
                    stats=stats,
                    seen=seen_battle_ids,
                    workers=workers,
                )

            # Progress after each parquet file
            log.info(
                "  Progress: %d parsed, %d errors | elapsed %s",
                stats.parsed_ok, stats.parse_errors, stats.elapsed(),
            )

        # Final flush of remaining rows
        acc.flush()
        final_counts = acc.total_rows()

    # ── Summary ───────────────────────────────────────────────────────────────
    log.info("\n" + "=" * 60)
    log.info("RUN COMPLETE")
    log.info("=" * 60)
    log.info(stats.summary())
    log.info("\nRow counts per table:")
    for table, count in final_counts.items():
        if count:
            log.info("  %-30s %d", table, count)
    log.info("\nOutput directory: %s", out_dir.resolve())
    if stats.parse_errors:
        log.warning("Error log: %s", error_log_path)

    return stats


# =============================================================================
# Serial worker
# =============================================================================

def _run_serial(
    log_series: "pd.Series",
    source_name: str,
    acc: TableAccumulator,
    err_log: ErrorLog,
    stats: RunStats,
    seen: set[str],
    dry_run: bool,
) -> None:
    total = len(log_series)
    for i, (idx, log_text) in enumerate(log_series.items()):
        if (i + 1) % 1000 == 0 or i == total - 1:
            log.info("    %d / %d  (%.0f%%)", i + 1, total, 100 * (i + 1) / total)

        if not isinstance(log_text, str) or not log_text.strip():
            stats.parse_errors += 1
            err_log.record(source_name, "", "Empty or non-string log")
            continue

        db, battle_id, error = _parse_log_row(log_text, source_name, i)

        if error:
            stats.parse_errors += 1
            err_log.record(source_name, battle_id or f"row_{i}", error)
            continue

        if battle_id in seen:
            stats.skipped_duplicate += 1
            continue
        seen.add(battle_id)

        if not dry_run:
            acc.add(db)
        stats.parsed_ok += 1


# =============================================================================
# Parallel worker
# =============================================================================

def _parallel_task(args: tuple) -> "tuple[dict[str, list[dict]], str, str, str]":
    """Top-level function (picklable) for ProcessPoolExecutor."""
    log_text, source_name, row_idx = args
    db, battle_id, error = _parse_log_row(log_text, source_name, row_idx)
    if error or db is None:
        return {}, battle_id, error, source_name
    # Serialise tables as plain dicts (ProcessPoolExecutor uses pickle)
    return db.tables, battle_id, "", source_name


def _run_parallel(
    log_series: "pd.Series",
    source_name: str,
    acc: TableAccumulator,
    err_log: ErrorLog,
    stats: RunStats,
    seen: set[str],
    workers: int,
) -> None:
    tasks = [
        (log_text, source_name, i)
        for i, log_text in enumerate(log_series)
        if isinstance(log_text, str) and log_text.strip()
    ]
    stats.parse_errors += len(log_series) - len(tasks)

    total = len(tasks)
    done = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_parallel_task, t): t for t in tasks}
        for fut in as_completed(futures):
            done += 1
            if done % 1000 == 0 or done == total:
                log.info("    %d / %d  (%.0f%%)", done, total, 100 * done / total)
            try:
                tables, battle_id, error, src = fut.result()
            except Exception as exc:
                stats.parse_errors += 1
                err_log.record(source_name, "", str(exc))
                continue

            if error:
                stats.parse_errors += 1
                err_log.record(src, battle_id or "", error)
                continue

            if battle_id in seen:
                stats.skipped_duplicate += 1
                continue
            seen.add(battle_id)

            # Re-wrap raw dict into a lightweight stub for TableAccumulator
            stub = _DictDB(tables)
            acc.add(stub)
            stats.parsed_ok += 1


class _DictDB:
    """Lightweight stand-in for InMemoryDB when tables arrive as plain dicts."""
    def __init__(self, tables: dict):
        self.tables = tables


# =============================================================================
# CLI
# =============================================================================

def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Parse VGC parquet battle logs → per-table parquet files",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/vgc_data"),
        help="Directory containing source *.parquet files",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/output"),
        help="Directory where per-table parquet files are written",
    )
    p.add_argument(
        "--log-col",
        default=None,
        help=(
            "Name of the column in the parquet file that contains the raw log text. "
            "If omitted, the runner auto-detects it."
        ),
    )
    p.add_argument(
        "--batch",
        type=int,
        default=5_000,
        metavar="N",
        help="Flush accumulated rows to disk every N rows (RAM control)",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=0,
        metavar="N",
        help="Number of parallel worker processes (0 or 1 = serial)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse without writing any output (for benchmarking / validation)",
    )
    return p


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    run(
        data_dir=args.data_dir,
        out_dir=args.out_dir,
        log_col=args.log_col,
        batch_size=args.batch,
        workers=args.workers,
        dry_run=args.dry_run,
    )