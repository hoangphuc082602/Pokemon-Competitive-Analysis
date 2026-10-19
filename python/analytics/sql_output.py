"""Write an aggregate DataFrame to MySQL with bounded string columns and indexes.

pandas creates TEXT columns, which MySQL cannot index without a key length, and `if_exists="replace"` drops the table
(and its indexes) on every load. This helper fixes the widths of the known text columns, writes the table and creates
the requested indexes right after.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import String, text

STRING_WIDTHS = {"regulation": 40, "rating_band": 12, "species": 60, "form": 80, "form_basis": 14, "month": 7,
                 "tera_type": 12, "species_a": 60, "species_b": 60, "game": 20, "band": 12}


def write_table(df: pd.DataFrame, name: str, engine, indexes: list[list[str]] | None = None) -> None:
    dtype = {c: String(w) for c, w in STRING_WIDTHS.items() if c in df.columns}
    df.to_sql(name, engine, if_exists="replace", index=False, chunksize=5000, dtype=dtype)
    with engine.begin() as conn:
        for i, cols in enumerate(indexes or [], start=1):
            missing = [c for c in cols if c not in df.columns]
            if missing:
                raise ValueError(f"{name}: cannot index missing column(s) {missing}")
            conn.execute(text(f"CREATE INDEX idx_{name}_{i} ON {name} ({', '.join(cols)})"))