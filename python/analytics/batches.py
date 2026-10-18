"""Shared reader: yield the team-slot table as DataFrames that contain whole battles only."""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pandas as pd
import pyarrow.parquet as pq


def battle_chunks(path: Path, columns: list[str]) -> Iterator[pd.DataFrame]:
    """The rows of one battle are contiguous but may straddle two row groups: the last battle of a group is
    carried over to the next one, so a team (or a pair of teams) is never split. `columns` must hold battle_id."""
    pf, carry = pq.ParquetFile(path), None
    for g in range(pf.num_row_groups):
        df = pf.read_row_group(g, columns=columns).to_pandas()
        if carry is not None:
            df = pd.concat([carry, df], ignore_index=True)
        if df.empty:
            carry = None
            continue
        last = df["battle_id"].iloc[-1]
        carry, df = df[df["battle_id"] == last], df[df["battle_id"] != last]
        if len(df):
            yield df
    if carry is not None and len(carry):
        yield carry