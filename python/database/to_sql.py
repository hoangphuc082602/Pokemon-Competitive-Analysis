"""Load data/output/<table>.parquet into MySQL, streaming one Parquet row group at a time.

Run from the repository root:
    python -m python.database.to_sql --dry-run                 # show the plan and run all checks, write nothing
    python -m python.database.to_sql                           # load every table that has a parquet file
    python -m python.database.to_sql --tables battle_field_state
    python -m python.database.to_sql --tables battle_leads --truncate    # reload a table from scratch

Safety rules (a failed 80M-row load is expensive, so everything that can be checked is checked first):
  * the target table must already exist (pandas would silently create an untyped one)
  * every parquet column must exist in the table
  * a non-empty table is refused unless --allow-non-empty (re-running would duplicate rows) or --truncate
  * each row group is inserted in ONE transaction, so a failure never leaves half a row group behind
"""
from __future__ import annotations

import argparse
import gc
import sys
import time
from pathlib import Path

import pyarrow.parquet as pq
from sqlalchemy import inspect, text

# parquet file name -> MySQL table
TABLES = {
    "players.parquet": "players",
    "battle.parquet": "battle",
    "battle_players.parquet": "battle_players",
    "battle_team_slot.parquet": "battle_team_slot",
    "battle_leads.parquet": "battle_leads",
    "battle_move.parquet": "battle_move",
    "battle_switch.parquet": "battle_switch",
    "battle_damage.parquet": "battle_damage",
    "battle_weather.parquet": "battle_weather",
    "battle_ability.parquet": "battle_ability",
    "battle_faint.parquet": "battle_faint",
    "battle_ko.parquet": "battle_ko",
    "battle_status.parquet": "battle_status",
    "battle_tera.parquet": "battle_tera",
    "battle_field_state.parquet": "battle_field_state",
}

DEFAULT_OUTPUT_DIR = Path("data/output")


class LoadError(RuntimeError):
    """A pre-flight check or a load step failed; the message says which table and why."""


def plan_imports(output_dir: Path, only: list[str] | None = None):
    """Return ([(parquet_path, table), ...] found, [parquet file names missing])."""
    tables = {f: t for f, t in TABLES.items() if only is None or t in only}
    unknown = set(only or []) - set(TABLES.values())
    if unknown:
        raise LoadError(f"Unknown table(s): {sorted(unknown)}. Known: {sorted(TABLES.values())}")
    found = [(output_dir / f, t) for f, t in tables.items() if (output_dir / f).exists()]
    missing = [f for f in tables if not (output_dir / f).exists()]
    return found, missing


def table_row_count(engine, table: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM `{table}`" if engine.dialect.name == "mysql"
                                 else f'SELECT COUNT(*) FROM "{table}"')).scalar_one()


def check_target(engine, parquet_path: Path, table: str, allow_non_empty: bool = False) -> int:
    """Pre-flight checks for one table. Returns the number of rows already in it."""
    insp = inspect(engine)
    if not insp.has_table(table):
        raise LoadError(f"{table}: table does not exist in the database (create it from the schema first)")

    table_cols = {c["name"] for c in insp.get_columns(table)}
    parquet_cols = set(pq.ParquetFile(parquet_path).schema_arrow.names)
    extra = sorted(parquet_cols - table_cols)
    if extra:
        raise LoadError(f"{table}: parquet columns not in the table: {extra}")

    existing = table_row_count(engine, table)
    if existing and not allow_non_empty:
        parquet_rows = pq.ParquetFile(parquet_path).metadata.num_rows
        if existing == parquet_rows:
            verdict = f"the parquet file has the same {parquet_rows:,} rows, so the table looks already loaded"
        elif existing < parquet_rows:
            verdict = f"the parquet file has {parquet_rows:,} rows, so the load looks INCOMPLETE ({parquet_rows - existing:,} missing)"
        else:
            verdict = f"the parquet file has only {parquet_rows:,} rows, so the table has {existing - parquet_rows:,} extra rows (loaded twice or from another source?)"
        raise LoadError(
            f"{table}: already has {existing:,} rows; {verdict}. "
            "Loading again would duplicate rows: use --truncate to reload from scratch "
            "or --allow-non-empty to append anyway."
        )
    return existing


def resume_point(parquet_path: Path, existing: int) -> int:
    """Index of the first row group not loaded yet, given `existing` rows already in the table.

    Every row group is committed atomically, so an interrupted load leaves exactly the first k row groups.
    Raises LoadError when `existing` is not on a row-group boundary (the table is not a clean prefix).
    """
    md = pq.ParquetFile(parquet_path).metadata
    done = 0
    for rg in range(md.num_row_groups):
        if done == existing:
            return rg
        done += md.row_group(rg).num_rows
    if done == existing:
        return md.num_row_groups
    raise LoadError(f"{parquet_path.stem}: the table has {existing:,} rows, which does not end on a row-group "
                    f"boundary of the parquet file ({done:,} rows): cannot resume safely, use --truncate")


def truncate_table(engine, table: str) -> None:
    with engine.begin() as conn:
        if engine.dialect.name == "mysql":
            conn.execute(text(f"TRUNCATE TABLE `{table}`"))
        else:
            conn.execute(text(f'DELETE FROM "{table}"'))


def import_parquet(parquet_path: Path, table: str, engine, batch_size: int = 1000, start_group: int = 0) -> int:
    """Append one parquet file to `table`, one row group (= one transaction) at a time.

    start_group skips the first row groups (already loaded); returns the number of rows imported by this call.
    """
    pf = pq.ParquetFile(parquet_path)
    total = pf.metadata.num_rows
    skipped = sum(pf.metadata.row_group(i).num_rows for i in range(start_group))
    imported = 0
    for rg in range(start_group, pf.num_row_groups):
        df = pf.read_row_group(rg).to_pandas()
        try:
            df.to_sql(table, engine, if_exists="append", index=False, method="multi", chunksize=batch_size)
        except Exception as exc:
            raise LoadError(f"{table}: failed in row group {rg + 1}/{pf.num_row_groups} "
                            f"after {imported:,} rows were committed: {exc}") from exc
        imported += len(df)
        print(f"  {table}: {skipped + imported:,}/{total:,} rows (row group {rg + 1}/{pf.num_row_groups})", flush=True)
        del df
        gc.collect()
    return imported


def main(argv=None, engine=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    ap.add_argument("--tables", nargs="+", help="only these tables (default: all that have a parquet file)")
    ap.add_argument("--batch-size", type=int, default=1000, help="rows per INSERT statement")
    ap.add_argument("--truncate", action="store_true", help="empty each target table before loading it")
    ap.add_argument("--allow-non-empty", action="store_true", help="append even if the table already has rows")
    ap.add_argument("--resume", action="store_true",
                    help="continue an interrupted load: skip the row groups already in the table (must end on a row-group boundary)")
    ap.add_argument("--dry-run", action="store_true", help="run every check, write nothing")
    args = ap.parse_args(argv)
    if args.resume and args.truncate:
        ap.error("--resume and --truncate cannot be combined")

    if engine is None:
        from python.database.db_connection import engine as default_engine
        engine = default_engine

    try:
        found, missing = plan_imports(args.output_dir, args.tables)
        for f in missing:
            print(f"SKIP  {f}: not found in {args.output_dir}")
        if not found:
            raise LoadError(f"No parquet files to load in {args.output_dir}")

        start_groups: dict[str, int] = {}
        for path, table in found:        # check everything BEFORE writing anything
            existing = check_target(engine, path, table, args.allow_non_empty or args.truncate or args.resume)
            rows = pq.ParquetFile(path).metadata.num_rows
            note = " [will TRUNCATE]" if args.truncate and existing else ""
            if args.resume:
                start_groups[table] = resume_point(path, existing)
                note = f" [resume at row group {start_groups[table] + 1}]" if existing else ""
            print(f"PLAN  {path.name} -> {table}: {rows:,} rows (table now has {existing:,})" + note)
        if args.dry_run:
            print("Dry run: nothing written.")
            return 0

        for path, table in found:
            if args.truncate:
                truncate_table(engine, table)
            start = time.time()
            n = import_parquet(path, table, engine, args.batch_size, start_groups.get(table, 0))
            print(f"DONE  {table}: {n:,} rows in {time.time() - start:,.0f}s")
    except LoadError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())