"""Sanity-check parser v2 output (species columns, player rows) without loading big tables into RAM.

    python -m python.data_quality.validate_v2_output --out-dir data/output_v2_test --probe urshifu

Prints, per event table: rows, % species empty, % species masked ('*'), % rows where species differs from
pokemon_name (nicknames). Then the species values containing --probe in leads/switch, and the number of
battle_players rows per battle (expected: exactly 2).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

SPECIES_TABLES = ["battle_leads", "battle_switch", "battle_move", "battle_faint",
                  "battle_status", "battle_ability", "battle_tera"]


def species_stats(path: Path) -> dict:
    n = empty = masked = differs = 0
    for b in pq.ParquetFile(path).iter_batches(columns=["pokemon_name", "species"], batch_size=1_000_000):
        sp, name = b.column("species"), b.column("pokemon_name")
        n += b.num_rows
        empty += pc.sum(pc.cast(pc.or_(pc.is_null(sp), pc.equal(sp, "")).fill_null(True), pa.int64())).as_py() or 0
        masked += pc.sum(pc.cast(pc.ends_with(sp, "*").fill_null(False), pa.int64())).as_py() or 0
        differs += pc.sum(pc.cast(pc.not_equal(sp, name).fill_null(False), pa.int64())).as_py() or 0
    return {"rows": n, "empty": empty, "masked": masked, "nickname": differs}


def probe_values(out_dir: Path, needle: str) -> pd.Series:
    total = pd.Series(dtype="int64")
    for table in ("battle_leads", "battle_switch"):
        for b in pq.ParquetFile(out_dir / f"{table}.parquet").iter_batches(columns=["species"], batch_size=1_000_000):
            sp = b.column("species")
            hit = pc.match_substring(sp, needle, ignore_case=True).fill_null(False)
            counts = pd.Series(sp.filter(hit).to_pylist(), dtype="object").value_counts()
            total = total.add(counts, fill_value=0)
    return total.astype("int64").sort_values(ascending=False)


def read_sample(path: Path, columns: list[str], max_rows: int) -> pd.DataFrame:
    """~max_rows rows spread evenly over the whole file (every k-th row group), whole battles only.

    Row groups are written per batch of battles, so a group holds contiguous battles; when sampling,
    the first and last battle of large groups are dropped because they may be cut at the boundary.
    """
    pf = pq.ParquetFile(path)
    total, n_groups = pf.metadata.num_rows, pf.num_row_groups
    step = max(1, -(-total // max_rows))          # ceil
    sampled = step > 1
    frames = []
    for g in range(0, n_groups, step):
        df = pf.read_row_group(g, columns=columns).to_pandas()
        if sampled and df["battle_id"].nunique() > 20:   # big groups may be cut mid-battle at their edges
            df = df[~df["battle_id"].isin([df["battle_id"].iloc[0], df["battle_id"].iloc[-1]])]
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", type=Path, required=True,
                    help="folder written by parser v2 (data/output holds v1 files without species)")
    ap.add_argument("--probe", default="urshifu")
    ap.add_argument("--max-rows", type=int, default=3_000_000,
                    help="rows sampled (spread over the file) from battle_team_slot / battle_players")
    args = ap.parse_args(argv)
    d = args.out_dir

    print(f"{'table':<16}{'rows':>12}{'species empty':>15}{'masked (*)':>12}{'name!=species':>15}")
    for t in SPECIES_TABLES:
        p = d / f"{t}.parquet"
        if not p.exists():
            print(f"{t:<16}  (missing)")
            continue
        if "species" not in pq.read_schema(p).names:
            print(f"{t:<16}  no 'species' column: written by parser v1 or an older runner.py")
            continue
        s = species_stats(p)
        pct = lambda x: f"{100 * x / max(s['rows'], 1):.2f}%"
        print(f"{t:<16}{s['rows']:>12,}{pct(s['empty']):>15}{pct(s['masked']):>12}{pct(s['nickname']):>15}")

    print(f"\nspecies containing '{args.probe}' in leads + switch:")
    print(probe_values(d, args.probe).head(10).to_string() or "  (none)")

    battle = d / "battle.parquet"
    if battle.exists():
        fmt = pq.read_table(battle, columns=["format_id"]).column("format_id")
        counts = pd.Series(fmt.to_pylist(), dtype="object").value_counts()
        print(f"\nbattle.format_id ({len(counts)} distinct, top 15):")
        print(counts.head(15).to_string())

    ts = d / "battle_team_slot.parquet"
    if ts.exists() and "form_status" in pq.read_schema(ts).names:
        slots = read_sample(ts, ["battle_id", "player_side", "form_status", "was_sent_out", "is_lead"], args.max_rows)
        print("\nbattle_team_slot form_status:")
        print(slots["form_status"].value_counts().to_string())
        per_side = slots.groupby(["battle_id", "player_side"]).agg(sent=("was_sent_out", "sum"), leads=("is_lead", "sum"))
        print("\nPokemon sent out per player (expected mostly 3-4):")
        print(per_side["sent"].value_counts().sort_index().to_string())
        print("is_lead per player (expected 2):")
        print(per_side["leads"].value_counts().sort_index().to_string())
        odd = per_side[per_side["leads"] != 2].reset_index().head(3)
        if len(odd):
            lt = pq.read_table(d / "battle_leads.parquet", columns=["battle_id", "username", "species", "lead_slot"],
                               filters=[("battle_id", "in", odd["battle_id"].tolist())]).to_pandas()
            print("\nexamples with is_lead != 2 (leads table rows for those battles):")
            print(lt.sort_values(["battle_id", "username", "lead_slot"]).to_string(index=False))

    bp = read_sample(d / "battle_players.parquet", ["battle_id"], args.max_rows)
    print("\nbattle_players rows per battle (expected 2):")
    per_battle = bp.groupby("battle_id").size()
    print(per_battle.value_counts().sort_index().to_string())
    odd_ids = per_battle[per_battle != 2].head(3).index.tolist()
    if odd_ids:
        rows = pq.read_table(d / "battle_players.parquet", filters=[("battle_id", "in", odd_ids)]).to_pandas()
        print("\nexamples with players != 2:")
        print(rows.to_string(index=False))
    bad = read_sample(d / "battle_players.parquet", ["battle_id", "rating_before"], args.max_rows)["rating_before"].dropna()
    print(f"\nrating_before: {len(bad):,} non-null, {int((bad < 800).sum()):,} below 800 (suspicious: avatar ids read as ratings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())