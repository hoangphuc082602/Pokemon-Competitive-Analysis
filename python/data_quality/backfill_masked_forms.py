"""Prototype (dry-run): resolve masked Showdown form names in ``battle_team_slot``.

Showdown hides the form of some Pokemon at team preview (``Urshifu-*``,
``Zacian-*``, ...). The real form usually appears later in battle events, so
this script recovers it from ``battle_leads`` and ``battle_switch``:

    battle_team_slot (battle_id, player_side)
        -> battle_players (battle_id, side) -> username
        -> battle_leads + battle_switch (battle_id, username, pokemon_name)
        -> same species (``Urshifu-*`` matches ``Urshifu-Rapid-Strike``)

Status per masked slot:
    resolved   exactly one matching form was seen in battle
    ambiguous  several forms seen (e.g. Greninja and Greninja-Ash)
    unknown    no matching form was seen (Pokemon probably not brought)
    no_player  (battle_id, player_side) not found in battle_players

It never writes to MySQL or to the output Parquet files. It prints a report and
writes one CSV under --report-dir.

    python -m python.data_quality.backfill_masked_forms --source 2024_part4
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

MASK = "*"
EVENT_COLS = ["battle_id", "username", "pokemon_name"]


def side_coverage(slots: pd.DataFrame, players: pd.DataFrame) -> float:
    """Share of distinct (battle_id, player_side) in slots found in battle_players."""
    have = slots[["battle_id", "player_side"]].drop_duplicates()
    keys = players[["battle_id", "side"]].drop_duplicates().rename(columns={"side": "player_side"})
    merged = have.merge(keys, on=["battle_id", "player_side"], how="left", indicator=True)
    return float((merged["_merge"] == "both").mean()) if len(merged) else 0.0


def _plain(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Copy with ``cols`` as plain Python-object strings (missing -> None), independent of pandas dtype."""
    df = df.copy()
    for c in cols:
        df[c] = df[c].astype(object).where(df[c].notna(), None)
    return df


def resolve_masked(slots: pd.DataFrame, players: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """One row per masked slot with status / resolved_name / candidates / brought_n.

    slots:   battle_id, player_side, slot_no, pokemon_name
    players: battle_id, side, username
    events:  battle_id, username, pokemon_name   (leads + switches)
    """
    slots = _plain(slots, ["battle_id", "player_side", "pokemon_name"])
    players = _plain(players, ["battle_id", "side", "username"])
    events = _plain(events, EVENT_COLS)
    masked = slots.loc[slots["pokemon_name"].str.endswith(MASK),
                       ["battle_id", "player_side", "slot_no", "pokemon_name"]].reset_index(drop=True)
    masked["slot_key"] = masked.index
    masked["prefix"] = masked["pokemon_name"].str[:-1].str.lower()   # 'urshifu-'
    masked["base"] = masked["prefix"].str.rstrip("-")                # 'urshifu'

    side_map = players[["battle_id", "side", "username"]].drop_duplicates(["battle_id", "side"])
    masked = masked.merge(side_map, left_on=["battle_id", "player_side"],
                          right_on=["battle_id", "side"], how="left").drop(columns="side")

    ev = events[EVENT_COLS].dropna().drop_duplicates()
    ev = ev[~ev["pokemon_name"].str.endswith(MASK)].copy()
    ev["name_lc"] = ev["pokemon_name"].str.lower()
    ev["root"] = ev["name_lc"].str.split("-").str[0]
    brought = (ev.groupby(["battle_id", "username"], observed=True)["root"].nunique()
                 .rename("brought_n").reset_index())

    joined = masked.merge(ev, on=["battle_id", "username"], how="left", suffixes=("", "_ev"))
    # a form matches if it is the base species ('Zacian') or starts with the prefix ('Zacian-')
    hit = [isinstance(n, str) and (n == b or n.startswith(p))
           for n, b, p in zip(joined["name_lc"], joined["base"], joined["prefix"])]
    found: dict[int, set[str]] = {}
    for key, name in zip(joined.loc[hit, "slot_key"], joined.loc[hit, "pokemon_name_ev"]):
        found.setdefault(int(key), set()).add(str(name))

    out = masked.drop(columns=["prefix", "base"]).merge(brought, on=["battle_id", "username"], how="left")
    out["brought_n"] = out["brought_n"].fillna(0).astype(int)
    out["candidates"] = [sorted(found.get(int(k), ())) for k in out["slot_key"]]
    out["n_candidates"] = out["candidates"].map(len)
    out["status"] = "unknown"
    out.loc[out["n_candidates"] == 1, "status"] = "resolved"
    out.loc[out["n_candidates"] > 1, "status"] = "ambiguous"
    out.loc[out["username"].isna(), "status"] = "no_player"
    out["resolved_name"] = out["candidates"].map(lambda c: c[0] if len(c) == 1 else None)
    return out.drop(columns="slot_key")


def read_filtered(path: Path, columns: list[str], keep, batch_size: int = 1_000_000) -> pd.DataFrame:
    """Stream a Parquet file in batches, keeping rows where keep(batch) is True (flat memory)."""
    parts = []
    for batch in pq.ParquetFile(path).iter_batches(columns=columns, batch_size=batch_size):
        sel = batch.filter(keep(batch))
        if sel.num_rows:
            df = sel.to_pandas()
            for c in df.columns:  # dictionary-encoded Parquet columns come back as categoricals
                if isinstance(df[c].dtype, pd.CategoricalDtype):
                    df[c] = df[c].astype(object)
            parts.append(df)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=columns)


def _in_ids(ids: list[str]):
    id_arr = pa.array(ids, type=pa.string())
    return lambda b: pc.is_in(b.column("battle_id"), value_set=id_arr.cast(b.schema.field("battle_id").type))


def probe_events(events: pd.DataFrame, needle: str, top: int = 15) -> pd.Series:
    """Most common event names containing ``needle`` (case-insensitive)."""
    names = events["pokemon_name"].dropna()
    return names[names.str.contains(needle, case=False, regex=False)].value_counts().head(top)


def explain(slots: pd.DataFrame, players: pd.DataFrame, events: pd.DataFrame, n: int, needle: str = "") -> None:
    """Print raw rows (repr, so stray spaces/case show up) for the first n masked slots."""
    ms = slots[slots["pokemon_name"].str.endswith(MASK)]
    if needle:
        ms = ms[ms["pokemon_name"].str.contains(needle, case=False, regex=False)]
    for r in ms.head(n).itertuples():
        print(f"\n--- battle {r.battle_id!r} slot {r.player_side!r}/{r.slot_no} name {r.pokemon_name!r}")
        print("players:", [(x.side, x.username) for x in players[players["battle_id"] == r.battle_id].itertuples()])
        print("events :", [(x.username, x.pokemon_name) for x in events[events["battle_id"] == r.battle_id].itertuples()])


def summarize(res: pd.DataFrame) -> str:
    if res.empty:
        return "No masked slots found."
    n = len(res)
    lines = [f"Masked slots: {n:,}"]
    for status, c in res["status"].value_counts().items():
        lines.append(f"  {status:<10} {c:>9,}  {c / n:6.1%}")
    lines.append("\nBy masked name (top 10):")
    top = res.groupby(["pokemon_name", "status"]).size().unstack(fill_value=0)
    top["total"] = top.sum(axis=1)
    lines.append(top.sort_values("total", ascending=False).head(10).to_string())
    unk = res[res["status"] == "unknown"]
    if len(unk):
        lines.append("\nHypothesis check (unknown = Pokemon not brought to the battle):")
        lines.append("  distinct species seen in battle for the owning player, unknown slots only:")
        lines.append(unk["brought_n"].value_counts().sort_index().to_string())
        lines.append(f"  share with brought_n >= 4: {(unk['brought_n'] >= 4).mean():.1%}  "
                     "(supports the hypothesis; brought_n < 4 is inconclusive because a Pokemon "
                     "that never entered the field leaves no event)")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output-dir", type=Path, default=Path("data/output"))
    ap.add_argument("--source", required=True,
                    help="substring of battle.replay_path that selects one source file, e.g. 2024_part4")
    ap.add_argument("--limit-battles", type=int, default=0, help="only use the first N battle_ids (0 = all)")
    ap.add_argument("--report-dir", type=Path, default=Path("data/mapping"))
    ap.add_argument("--min-side-coverage", type=float, default=0.99)
    ap.add_argument("--explain", type=int, default=0, help="print raw rows of the first N masked slots (filtered by --probe)")
    ap.add_argument("--probe", default="", help="print the most common event names containing this text, e.g. urshifu")
    args = ap.parse_args(argv)
    d = args.output_dir

    battle = read_filtered(d / "battle.parquet", ["battle_id", "replay_path"],
                           lambda b: pc.match_substring(b.column("replay_path"), pattern=args.source))
    ids = sorted(battle["battle_id"].unique())
    if args.limit_battles:
        ids = ids[: args.limit_battles]
    if not ids:
        print(f"No battles with replay_path containing '{args.source}'.", file=sys.stderr)
        return 1
    print(f"Source '{args.source}': {len(ids):,} battles")

    keep = _in_ids(ids)
    slots = read_filtered(d / "battle_team_slot.parquet", ["battle_id", "player_side", "slot_no", "pokemon_name"], keep)
    players = read_filtered(d / "battle_players.parquet", ["battle_id", "side", "username"], keep)
    leads = read_filtered(d / "battle_leads.parquet", EVENT_COLS, keep)
    switches = read_filtered(d / "battle_switch.parquet", EVENT_COLS, keep)

    print("player_side values:", sorted(slots["player_side"].dropna().unique()))
    print("side values:       ", sorted(players["side"].dropna().unique()))
    cov = side_coverage(slots, players)
    print(f"side join coverage: {cov:.2%}")
    if cov < args.min_side_coverage:
        print("ABORT: player_side and side do not line up; fix this before resolving forms.", file=sys.stderr)
        return 1

    events = pd.concat([leads, switches], ignore_index=True)
    starred = events["pokemon_name"].fillna("").str.endswith(MASK)
    print(f"event rows: {len(events):,} | with a masked name ('*'): {int(starred.sum()):,}")
    if starred.any():
        print(events.loc[starred, "pokemon_name"].value_counts().head(5).to_string())
    if args.probe:
        print(f"\nEvent names containing '{args.probe}':")
        print(probe_events(events, args.probe).to_string())

    res = resolve_masked(slots, players, events)
    if args.explain:
        explain(slots, players, events, args.explain, args.probe)
        shown = res
        if args.probe:
            shown = res[res["pokemon_name"].str.contains(args.probe, case=False, regex=False)]
        print("\nresolver output for these slots:")
        print(shown.head(args.explain)[["battle_id", "player_side", "username", "status", "resolved_name", "n_candidates", "brought_n"]].to_string())
        print("pandas", pd.__version__, "| pyarrow", pa.__version__)
        print("dtypes:", {k: str(v) for k, v in {**slots.dtypes, **events.dtypes}.items()})
    print(summarize(res))

    args.report_dir.mkdir(parents=True, exist_ok=True)
    out = args.report_dir / f"masked_resolution_{args.source.replace(' ', '_')}.csv"
    res.assign(candidates=res["candidates"].map(lambda c: ";".join(c))).to_csv(out, index=False)
    print(f"\nReport written to {out} (dry-run: no Parquet or MySQL data was changed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())