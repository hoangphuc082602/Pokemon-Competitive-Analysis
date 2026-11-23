"""Export pre-computed aggregates as static JSON for the web app (ADR-013).

    python -m python.analytics.export_web --agg data/aggregates --out web/public/data

Reads pokemon_usage_stats (Parquet, in batches; CSV fallback in chunks) and regulation_totals, writes
    manifest.json                          schema version, snapshot date, regulations, bands, row counts, file sizes
    team_usage/<regulation>__<band>.json   form-level team usage of one regulation x rating band
    species_forms.json                     species <-> form mapping of every form in the team usage files
    partners/<regulation>__<band>.json     per species: its most frequent team partners with lift (pokemon_partner_stats)
    matchups/<regulation>__<band>.json     per species: team-level matchups furthest below / above the log5 expectation
                                           (pokemon_matchup_stats)
    trend/<regulation>__<band>.json        upload months with player-battles and the `tail` flag, and per species its
                                           monthly team usage (pokemon_usage_monthly; 'unknown' month left out)
    tera/<regulation>__<band>.json         per species: Tera rate, win rate with / without Tera, Tera type split
                                           (pokemon_tera_summary, pokemon_tera_types)
Partners, matchups, trend and Tera are species level (all forms together), as built by partner_stats / matchup_stats /
usage_trend / tera_stats; when those tables are absent their datasets are empty. Lift is co-occurrence, not synergy;
matchups are about teams containing the species, not about the species on the field. Tail months stay in the trend
files, flagged, for the UI to leave out of charts. Win rates with and without Tera are not comparable (survivorship).
Business rules are applied here so the browser only displays (docs/ai-onboarding/03-BUSINESS-RULES):
    population  completed VGC battles, unit = player-battle (inherited from pokemon_usage)
    BR-05       one row per form (poke_id x form_basis of pokemon_usage_stats), never merged: masked families
                never sent out are a '<species> (form unknown)' row, forms missing from the master data a
                species-level 'species_only' row; BR-06: 'observed' rows count only teams where the form was revealed
    BR-08       every band is its own file; 'all' comes from the 'all' rows of the input, never from a sum of bands
    BR-09       win_rate_delta = win rate - the band's own baseline (all species of that regulation x band, before the n filter)
    BR-10       rows (forms) with n < 100 player-battles are dropped; partner pairs with n < 100 teams and matchups
                with n < 100 battles likewise; trend points with n < 100 teams; Tera rows with < 100 sent-out
                appearances, a win rate with / without Tera on < 100 games (null), the type split on < 100 Tera events
Output columns are an allow-list; usernames, replay / battle ids and player-level columns are refused (ExportError).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from python.analytics.pokemon_usage import wilson

SCHEMA_VERSION = 4              # v4: trend + tera datasets (#14); v3: partners + matchups (#13); v2: one row per form (#24)
MIN_N = 100
KEYS = ["regulation", "rating_band", "species_id", "species", "poke_id", "form", "form_basis"]
NO_FORM = -1                     # poke_id of unobserved / species_only rows while grouping (NULL in the output)
COUNTS = ["appearances", "wins", "leads"]
ROW_COLUMNS = ["species_id", "species", "poke_id", "form", "form_basis", "label", "n", "usage_share", "win_rate", "win_ci_low", "win_ci_high",
               "win_rate_delta", "lead_rate"]
FILE_COLUMNS = ["regulation", "rating_band", "player_battles", "baseline_win_rate", "min_n", "rows"]
PAIR_KEYS = ["regulation", "rating_band", "species_a", "species_b", "species_a_id", "species_b_id"]
PARTNER_IN = PAIR_KEYS + ["teams_both", "share_of_a", "share_of_b", "lift", "win_rate", "win_ci_low", "win_ci_high",
                          "win_rate_delta"]
MATCHUP_IN = PAIR_KEYS + ["battles", "win_rate", "win_ci_low", "win_ci_high", "win_rate_delta", "expected_win_rate",
                          "win_rate_vs_expected", "z_vs_expected"]
PARTNER_COLUMNS = ["species_id", "species", "n", "share", "lift", "win_rate", "win_ci_low", "win_ci_high", "win_rate_delta"]
OPPONENT_COLUMNS = ["species_id", "species", "n", "win_rate", "win_ci_low", "win_ci_high", "win_rate_delta",
                    "expected_win_rate", "win_rate_vs_expected", "z_vs_expected"]
PAIR_FILE_COLUMNS = ["regulation", "rating_band", "min_n", "rows"]
MONTHLY_IN = ["regulation", "month", "rating_band", "species", "species_id", "appearances", "player_battles", "tail",
              "usage_share", "win_rate", "win_ci_low", "win_ci_high"]
POINT_COLUMNS = ["month", "n", "usage_share", "win_rate", "win_ci_low", "win_ci_high"]
TREND_FILE_COLUMNS = ["regulation", "rating_band", "min_n", "months", "rows"]
TERA_IN = ["regulation", "rating_band", "species", "species_id", "sent_out", "tera_events", "tera_rate",
           "tera_rate_ci_low", "tera_rate_ci_high", "win_rate_tera", "win_rate_no_tera"]
TERA_TYPES_IN = ["regulation", "rating_band", "species_id", "tera_type", "events", "type_share"]
TERA_COLUMNS = ["species_id", "species", "n", "tera_events", "tera_rate", "tera_rate_ci_low", "tera_rate_ci_high",
                "win_rate_tera", "win_rate_no_tera", "types"]
TERA_TYPE_COLUMNS = ["tera_type", "events", "type_share"]
TOP_PARTNERS = 12               # most frequent partners kept per species
TOP_OPPONENTS = 8               # matchups kept per species at each end of z_vs_expected
FORBIDDEN = re.compile(r"user|replay|battle_id|player_side|^side$|^p[12]_|rating_before|nickname|pokemon_name", re.I)
BAND_ORDER = ["all", "below_1200", "1200_1399", "1400_1499", "1500_plus", "unknown"]


class ExportError(RuntimeError):
    """The export refused to write (forbidden column, missing input)."""


def check_columns(columns, where: str) -> None:
    bad = [c for c in columns if FORBIDDEN.search(str(c))]
    if bad:
        raise ExportError(f"forbidden column(s) {bad} in {where}: personal / battle-level data is never exported")


def _usage_batches(agg: Path, batch_size: int):
    """Form-level partial sums of pokemon_usage_stats, one DataFrame per batch."""
    pq_path, csv_path = agg / "pokemon_usage_stats.parquet", agg / "pokemon_usage_stats.csv"
    if pq_path.exists():
        pf = pq.ParquetFile(pq_path)
        check_columns(pf.schema_arrow.names, pq_path.name)
        batches = (b.to_pandas() for b in pf.iter_batches(columns=KEYS + COUNTS, batch_size=batch_size))
    elif csv_path.exists():
        check_columns(pd.read_csv(csv_path, nrows=0).columns, csv_path.name)
        batches = pd.read_csv(csv_path, usecols=KEYS + COUNTS, chunksize=batch_size)
    else:
        raise ExportError(f"pokemon_usage_stats.parquet/.csv not found in {agg}")
    for df in batches:
        df = df.assign(regulation=df["regulation"].astype(str), rating_band=df["rating_band"].astype(str),
                       species=df["species"].astype(str), species_id=df["species_id"].astype("int64"),
                       poke_id=pd.to_numeric(df["poke_id"], errors="coerce").fillna(NO_FORM).astype("int64"),
                       form=df["form"].where(df["form"].notna(), "").astype(str),
                       form_basis=df["form_basis"].astype(str))
        yield df.groupby(KEYS, as_index=False)[COUNTS].sum()


def _totals(agg: Path) -> pd.DataFrame:
    totals = pd.read_csv(agg / "regulation_totals.csv")
    check_columns(totals.columns, "regulation_totals.csv")
    return totals.assign(regulation=totals["regulation"].astype(str), rating_band=totals["rating_band"].astype(str))


def team_usage(agg: Path, batch_size: int = 500_000) -> pd.DataFrame:
    """Form-level team usage per regulation x band with band baseline, delta and Wilson interval (n < 100 dropped)."""
    totals = _totals(agg)
    parts = list(_usage_batches(agg, batch_size))
    if not parts:
        raise ExportError("pokemon_usage_stats is empty")
    g = pd.concat(parts, ignore_index=True).groupby(KEYS, as_index=False)[COUNTS].sum()
    base = g.groupby(["regulation", "rating_band"])[["wins", "appearances"]].transform("sum")
    g["baseline_win_rate"] = base["wins"] / base["appearances"]          # BR-09: before the n filter
    g = g.merge(totals[["regulation", "rating_band", "player_battles"]], on=["regulation", "rating_band"], how="left")
    if g["player_battles"].isna().any():
        missing = g.loc[g["player_battles"].isna(), ["regulation", "rating_band"]].drop_duplicates().values.tolist()
        raise ExportError(f"regulation_totals has no row for {missing}")
    g = g[g["appearances"] >= MIN_N].copy()                               # BR-10
    g["n"] = g["appearances"].astype("int64")
    g["usage_share"] = g["appearances"] / g["player_battles"]
    g["win_rate"] = g["wins"] / g["appearances"]
    g["win_rate_delta"] = g["win_rate"] - g["baseline_win_rate"]
    g["win_ci_low"], g["win_ci_high"] = wilson(g["wins"], g["appearances"])
    g["lead_rate"] = g["leads"] / g["appearances"]
    g["label"] = [_label(*v) for v in g[["species", "poke_id", "form", "form_basis"]].itertuples(index=False)]
    dup = g[g.duplicated(["regulation", "rating_band", "label"], keep=False)]
    if len(dup):
        raise ExportError(f"rows share a label: {dup[['regulation', 'rating_band', 'label']].values.tolist()[:5]}")
    return g.sort_values(["regulation", "rating_band", "n", "label"], ascending=[True, True, False, True]).reset_index(drop=True)


def _batches(agg: Path, table: str, columns: list[str], batch_size: int):
    """Batches of the given columns of an aggregate table (Parquet, else CSV in chunks); None if the table was not built.
    Raises ExportError on a forbidden column or when a requested column is missing."""
    pq_path, csv_path = agg / f"{table}.parquet", agg / f"{table}.csv"
    if pq_path.exists():
        names = pq.ParquetFile(pq_path).schema_arrow.names
    elif csv_path.exists():
        names = list(pd.read_csv(csv_path, nrows=0).columns)
    else:
        return None
    path = pq_path if pq_path.exists() else csv_path
    check_columns(names, path.name)
    missing = [c for c in columns if c not in names]
    if missing:
        raise ExportError(f"{path.name} has no column(s) {missing}")
    if path is pq_path:
        return (b.to_pandas() for b in pq.ParquetFile(pq_path).iter_batches(columns=columns, batch_size=batch_size))
    return pd.read_csv(csv_path, usecols=columns, chunksize=batch_size)


def _pair_rows(agg: Path, table: str, columns: list[str], n_col: str, batch_size: int) -> pd.DataFrame | None:
    """Rows of an aggregate pair table with n >= MIN_N (BR-10), read in batches; None if the table was not built."""
    batches = _batches(agg, table, columns, batch_size)
    if batches is None:
        return None
    parts = [df[pd.to_numeric(df[n_col]) >= MIN_N] for df in batches]
    df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=columns)
    df = df[columns].astype({c: str for c in ["regulation", "rating_band", "species_a", "species_b"]})
    return df.astype({"species_a_id": "int64", "species_b_id": "int64", n_col: "int64"})


def _owner_frame(t: pd.DataFrame, owner: str, other: str, extra: dict[str, str]) -> pd.DataFrame:
    """Rows of a pair table seen from `owner`: owner_id / owner, then the other species as species_id / species."""
    cols = {"regulation": t["regulation"], "rating_band": t["rating_band"],
            "owner_id": t[f"species_{owner}_id"], "owner": t[f"species_{owner}"],
            "species_id": t[f"species_{other}_id"], "species": t[f"species_{other}"]}
    return pd.DataFrame({**cols, **{new: t[old] for new, old in extra.items()}})


def partner_lists(agg: Path, batch_size: int = 500_000) -> pd.DataFrame | None:
    """Each species' TOP_PARTNERS most frequent partners (n = teams with both, n >= 100) per regulation x band.
    A pair A-B is listed under A with share P(B | A) and under B with share P(A | B); lift and win rate are shared."""
    t = _pair_rows(agg, "pokemon_partner_stats", PARTNER_IN, "teams_both", batch_size)
    if t is None:
        return None
    same = {c: c for c in ["lift", "win_rate", "win_ci_low", "win_ci_high", "win_rate_delta"]}
    d = pd.concat([_owner_frame(t, "a", "b", {"n": "teams_both", "share": "share_of_a", **same}),
                   _owner_frame(t, "b", "a", {"n": "teams_both", "share": "share_of_b", **same})], ignore_index=True)
    d = d.sort_values(["regulation", "rating_band", "owner", "n", "species"], ascending=[True, True, True, False, True])
    return d.groupby(["regulation", "rating_band", "owner_id"], sort=False).head(TOP_PARTNERS).reset_index(drop=True)


def matchup_lists(agg: Path, batch_size: int = 500_000) -> pd.DataFrame | None:
    """Each species' team-level matchups (n = battles, n >= 100) per regulation x band: the TOP_OPPONENTS lowest and
    TOP_OPPONENTS highest z_vs_expected (win rate against the log5 expectation), lowest first."""
    t = _pair_rows(agg, "pokemon_matchup_stats", MATCHUP_IN, "battles", batch_size)
    if t is None:
        return None
    d = _owner_frame(t, "a", "b", {"n": "battles", **{c: c for c in OPPONENT_COLUMNS[3:]}})
    d = d.sort_values(["regulation", "rating_band", "owner", "z_vs_expected", "species"])
    g = d.groupby(["regulation", "rating_band", "owner_id"], sort=False)
    keep = pd.concat([g.head(TOP_OPPONENTS), g.tail(TOP_OPPONENTS)])
    return d.loc[d.index.isin(keep.index)].reset_index(drop=True)


def trend_series(agg: Path, batch_size: int = 500_000) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """Monthly team usage (pokemon_usage_monthly) per regulation x band: (months, points). months lists every upload
    month with its player-battles and `tail` flag (before the n filter); points are species-months with n >= MIN_N
    teams (BR-10). The 'unknown' month (no upload time) is not a month and is left out. None if the table was not built."""
    try:
        batches = _batches(agg, "pokemon_usage_monthly", MONTHLY_IN, batch_size)
    except ExportError as e:
        if "rating_band" in str(e):
            raise ExportError(f"{e}: pokemon_usage_monthly predates rating bands, rerun python -m python.analytics.usage_trend")
        raise
    if batches is None:
        return None
    month_parts, point_parts = [], []
    for df in batches:
        df = df[df["month"].astype(str) != "unknown"].astype({"regulation": str, "month": str, "rating_band": str,
                                                               "species": str})
        month_parts.append(df[["regulation", "rating_band", "month", "player_battles", "tail"]].drop_duplicates())
        point_parts.append(df[pd.to_numeric(df["appearances"]) >= MIN_N])
    if not month_parts:                                   # table built but empty
        return None
    months = pd.concat(month_parts, ignore_index=True).drop_duplicates(["regulation", "rating_band", "month"])
    months = months.astype({"player_battles": "int64"}).assign(tail=months["tail"].astype(str).str.lower() == "true")
    points = pd.concat(point_parts, ignore_index=True).rename(columns={"appearances": "n"})
    points = points.astype({"species_id": "int64", "n": "int64"})
    return (months.sort_values(["regulation", "rating_band", "month"]).reset_index(drop=True),
            points.sort_values(["regulation", "rating_band", "species", "month"]).reset_index(drop=True))


def _write_trend_files(out: Path, trend: tuple[pd.DataFrame, pd.DataFrame] | None) -> list[dict]:
    files = []
    if trend is None:
        return files
    months, points = trend
    floats = POINT_COLUMNS[2:]
    for (reg, band), m in months.groupby(["regulation", "rating_band"], sort=False):
        p = points[(points["regulation"] == reg) & (points["rating_band"] == band)].copy()
        check_columns(p.columns, "trend rows")
        p[floats] = p[floats].astype(float).round(5)
        rows = [{"species_id": int(sid), "species": str(sp),
                 "points": [{"month": str(r.month), "n": int(r.n), **{c: float(getattr(r, c)) for c in floats}}
                            for r in g[POINT_COLUMNS].itertuples(index=False)]}
                for (sid, sp), g in p.groupby(["species_id", "species"], sort=False)]
        rows.sort(key=lambda r: (r["species"], r["species_id"]))
        payload = {"regulation": reg, "rating_band": band, "min_n": MIN_N,
                   "months": [{"month": str(r.month), "player_battles": int(r.player_battles), "tail": bool(r.tail)}
                              for r in m.itertuples(index=False)],
                   "rows": rows}
        if list(payload) != TREND_FILE_COLUMNS or any(list(q) != POINT_COLUMNS for r in rows for q in r["points"]):
            raise ExportError("trend file keys are not the allow-list")
        rel = f"trend/{reg}__{band}.json"
        files.append({"regulation": reg, "rating_band": band, "path": rel, "rows": len(rows),
                      "bytes": _write_json(out / rel, payload)})
    files.sort(key=lambda f: (f["regulation"], _band_key(f["rating_band"])))
    return files


def tera_tables(agg: Path, batch_size: int = 500_000) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """(summary, types) of pokemon_tera_summary / pokemon_tera_types per regulation x band. Species rows need n >= MIN_N
    sent-out appearances (the Tera rate's denominator, BR-10); a win rate with / without Tera is NaN when its own number
    of games is below MIN_N, and the type split is kept only for species with >= MIN_N Tera events.
    None if the summary was not built."""
    batches = _batches(agg, "pokemon_tera_summary", TERA_IN, batch_size)
    if batches is None:
        return None
    parts = [df[pd.to_numeric(df["sent_out"]) >= MIN_N] for df in batches]
    if not parts:                                         # table built but empty
        return None
    s = pd.concat(parts, ignore_index=True).astype({"regulation": str, "rating_band": str, "species": str,
                                                    "species_id": "int64", "sent_out": "int64", "tera_events": "int64"})
    s["win_rate_tera"] = s["win_rate_tera"].astype(float).where(s["tera_events"] >= MIN_N)
    s["win_rate_no_tera"] = s["win_rate_no_tera"].astype(float).where(s["sent_out"] - s["tera_events"] >= MIN_N)
    keys = ["regulation", "rating_band", "species_id"]
    t_batches = _batches(agg, "pokemon_tera_types", TERA_TYPES_IN, batch_size)
    t_parts = list(t_batches) if t_batches is not None else []
    t = pd.concat(t_parts, ignore_index=True) if t_parts else pd.DataFrame(columns=TERA_TYPES_IN)
    t = t.astype({"regulation": str, "rating_band": str, "species_id": "int64", "tera_type": str, "events": "int64"})
    t = t.merge(s.loc[s["tera_events"] >= MIN_N, keys], on=keys)
    return (s.sort_values(["regulation", "rating_band", "species"]).reset_index(drop=True),
            t.sort_values(keys + ["events", "tera_type"], ascending=[True, True, True, False, True]).reset_index(drop=True))


def _write_tera_files(out: Path, tera: tuple[pd.DataFrame, pd.DataFrame] | None) -> list[dict]:
    files = []
    if tera is None:
        return files
    summary, types = tera
    check_columns(list(summary.columns) + list(types.columns), "tera rows")
    rates = ["tera_rate", "tera_rate_ci_low", "tera_rate_ci_high", "win_rate_tera", "win_rate_no_tera"]
    for (reg, band), s in summary.groupby(["regulation", "rating_band"], sort=False):
        t = types[(types["regulation"] == reg) & (types["rating_band"] == band)]
        split = {sid: [{"tera_type": str(r.tera_type), "events": int(r.events), "type_share": round(float(r.type_share), 5)}
                       for r in g.itertuples(index=False)] for sid, g in t.groupby("species_id", sort=False)}
        rows = [{"species_id": int(r.species_id), "species": str(r.species), "n": int(r.sent_out),
                 "tera_events": int(r.tera_events),
                 **{c: None if pd.isna(getattr(r, c)) else round(float(getattr(r, c)), 5) for c in rates},
                 "types": split.get(int(r.species_id), [])} for r in s.itertuples(index=False)]
        payload = {"regulation": reg, "rating_band": band, "min_n": MIN_N, "rows": rows}
        if list(payload) != PAIR_FILE_COLUMNS or any(list(r) != TERA_COLUMNS for r in rows) \
                or any(list(x) != TERA_TYPE_COLUMNS for r in rows for x in r["types"]):
            raise ExportError("tera file keys are not the allow-list")
        rel = f"tera/{reg}__{band}.json"
        files.append({"regulation": reg, "rating_band": band, "path": rel, "rows": len(rows),
                      "bytes": _write_json(out / rel, payload)})
    files.sort(key=lambda f: (f["regulation"], _band_key(f["rating_band"])))
    return files


def _pair_payload(reg: str, band: str, g: pd.DataFrame, columns: list[str], key: str) -> dict:
    check_columns(g.columns, f"{key} rows")
    g = g.copy()
    floats = columns[columns.index("n") + 1:]
    g[floats] = g[floats].astype(float).round(5)
    rows = []
    for (owner_id, owner), h in g.groupby(["owner_id", "owner"], sort=False):
        items = [{"species_id": int(r.species_id), "species": str(r.species), "n": int(r.n),
                  **{c: float(getattr(r, c)) for c in floats}} for r in h[columns].itertuples(index=False)]
        rows.append({"species_id": int(owner_id), "species": str(owner), key: items})
    rows.sort(key=lambda r: (r["species"], r["species_id"]))
    payload = {"regulation": reg, "rating_band": band, "min_n": MIN_N, "rows": rows}
    if list(payload) != PAIR_FILE_COLUMNS or any(list(i) != columns for r in rows for i in r[key]):
        raise ExportError(f"{key} file keys are not the allow-list")
    return payload


def _write_pair_files(out: Path, dataset: str, d: pd.DataFrame | None, columns: list[str], key: str) -> list[dict]:
    files = []
    if d is None:
        return files
    for (reg, band), g in d.groupby(["regulation", "rating_band"], sort=False):
        rel = f"{dataset}/{reg}__{band}.json"
        payload = _pair_payload(reg, band, g, columns, key)
        size = _write_json(out / rel, payload)
        files.append({"regulation": reg, "rating_band": band, "path": rel, "rows": len(payload["rows"]), "bytes": size})
    files.sort(key=lambda f: (f["regulation"], _band_key(f["rating_band"])))
    return files


def _label(species: str, poke_id: int, form: str, form_basis: str) -> str:
    """Display name of a row: the form ('calyrex-shadow' -> 'Calyrex-Shadow'), or the species with why it has no form.
    A form revealed in battle is a different population from the same form named at team preview (BR-06), e.g.
    'Zacian-Crowned' and 'Zacian-Crowned (seen in battle)': two rows, never summed, never the same label."""
    if poke_id != NO_FORM and form:
        name = "-".join(part.capitalize() for part in form.split("-"))
        return f"{name} (seen in battle)" if form_basis == "observed" else name
    return f"{species} (form unknown)" if form_basis == "unobserved" else f"{species} (form not in master data)"


def _records(df: pd.DataFrame) -> list[dict]:
    check_columns(df.columns, "team_usage rows")
    out = df[ROW_COLUMNS].copy()
    floats = ROW_COLUMNS[ROW_COLUMNS.index("n") + 1:]
    out[floats] = out[floats].astype(float).round(5)
    return [{"species_id": int(r.species_id), "species": str(r.species),
             "poke_id": None if int(r.poke_id) == NO_FORM else int(r.poke_id), "form": str(r.form) or None,
             "form_basis": str(r.form_basis), "label": str(r.label), "n": int(r.n),
             **{c: float(getattr(r, c)) for c in floats}} for r in out.itertuples(index=False)]


def _write_json(path: Path, obj) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def _band_key(band: str) -> int:
    return BAND_ORDER.index(band) if band in BAND_ORDER else len(BAND_ORDER)


def export(agg: Path, out: Path, batch_size: int = 500_000, snapshot_date: str | None = None) -> dict:
    """Write the web data files and manifest.json under `out`; returns the manifest."""
    agg, out = Path(agg), Path(out)
    usage = team_usage(agg, batch_size)          # validates the inputs before anything is written or removed
    totals = _totals(agg)
    partners, matchups = partner_lists(agg, batch_size), matchup_lists(agg, batch_size)
    trend, tera = trend_series(agg, batch_size), tera_tables(agg, batch_size)
    for dataset in ("team_usage", "partners", "matchups", "trend", "tera"):   # files of an earlier export would be deployed but unlisted
        for old in (out / dataset).glob("*.json"):
            old.unlink()
    files = []
    for (reg, band), g in usage.groupby(["regulation", "rating_band"], sort=False):
        payload = {"regulation": reg, "rating_band": band, "player_battles": int(g["player_battles"].iloc[0]),
                   "baseline_win_rate": round(float(g["baseline_win_rate"].iloc[0]), 5), "min_n": MIN_N,
                   "rows": _records(g)}
        if list(payload) != FILE_COLUMNS:
            raise ExportError(f"team_usage file keys {list(payload)} are not the allow-list {FILE_COLUMNS}")
        rel = f"team_usage/{reg}__{band}.json"
        size = _write_json(out / rel, payload)
        files.append({"regulation": reg, "rating_band": band, "path": rel, "rows": len(payload["rows"]), "bytes": size})
    files.sort(key=lambda f: (f["regulation"], _band_key(f["rating_band"])))
    forms = usage.loc[usage["poke_id"] != NO_FORM, ["species", "form"]].drop_duplicates().sort_values(["species", "form"])
    mapping = [{"species": str(r.species), "form": str(r.form)} for r in forms.itertuples(index=False)]
    forms_file = {"path": "species_forms.json", "rows": len(mapping), "bytes": _write_json(out / "species_forms.json", mapping)}
    regs = []
    for reg in sorted(usage["regulation"].unique()):
        t = totals[(totals["regulation"] == reg) & (totals["rating_band"] == "all")]
        regs.append({"id": reg,
                     "battles": int(t["battles"].iloc[0]) if len(t) and pd.notna(t["battles"].iloc[0]) else None,
                     "player_battles": int(t["player_battles"].iloc[0]) if len(t) else None,
                     "bands": [f["rating_band"] for f in files if f["regulation"] == reg]})
    if snapshot_date is None:
        src = max((p.stat().st_mtime for p in agg.glob("pokemon_usage_stats.*")), default=None)
        snapshot_date = dt.date.fromtimestamp(src).isoformat() if src else dt.date.today().isoformat()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "snapshot_date": snapshot_date,
        "min_n": MIN_N,
        "population": "completed VGC battles; unit = player-battle; one row per form (masked / unlisted forms at species level)",
        "totals": {"battles": sum(r["battles"] or 0 for r in regs),
                   "player_battles": sum(r["player_battles"] or 0 for r in regs)},
        "regulations": regs,
        "bands": sorted({f["rating_band"] for f in files}, key=_band_key),
        "datasets": {"team_usage": files, "species_forms": forms_file,
                     "partners": _write_pair_files(out, "partners", partners, PARTNER_COLUMNS, "partners"),
                     "matchups": _write_pair_files(out, "matchups", matchups, OPPONENT_COLUMNS, "opponents"),
                     "trend": _write_trend_files(out, trend), "tera": _write_tera_files(out, tera)},
    }
    _write_json(out / "manifest.json", manifest)
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agg", type=Path, default=Path("data/aggregates"))
    ap.add_argument("--out", type=Path, default=Path("web/public/data"))
    ap.add_argument("--snapshot-date", default=None, type=lambda v: dt.date.fromisoformat(v).isoformat(),
                    help="ISO date (YYYY-MM-DD) of the data snapshot (default: aggregate file date)")
    args = ap.parse_args(argv)

    m = export(args.agg, args.out, snapshot_date=args.snapshot_date)
    files = m["datasets"]["team_usage"]
    on_disk = {f["path"]: (args.out / f["path"]).stat().st_size for f in files}
    print(f"schema v{m['schema_version']}, snapshot {m['snapshot_date']}, n >= {m['min_n']}")
    print(f"regulations ({len(m['regulations'])}): " + ", ".join(r["id"] for r in m["regulations"]))
    print(f"bands ({len(m['bands'])}): " + ", ".join(m["bands"]))
    print(f"totals: {m['totals']['battles']:,} battles, {m['totals']['player_battles']:,} player-battles")
    print(f"team_usage: {len(files)} files, {sum(f['rows'] for f in files):,} rows, "
          f"{sum(on_disk.values()) / 1024:,.1f} KiB, largest {max(on_disk.values(), default=0) / 1024:,.1f} KiB")
    for f in files:
        print(f"  {f['path']}: {f['rows']} rows, {f['bytes']:,} B")
    basis = {}
    for f in files:
        for r in json.loads((args.out / f["path"]).read_text(encoding="utf-8"))["rows"]:
            basis[r["form_basis"]] = basis.get(r["form_basis"], 0) + 1
    sf = m["datasets"]["species_forms"]
    print("rows per form_basis: " + ", ".join(f"{k} {v:,}" for k, v in sorted(basis.items())))
    print(f"species_forms.json: {sf['rows']} forms, {sf['bytes']:,} B")
    for ds, key, job in (("partners", "partners", "partner_stats"), ("matchups", "opponents", "matchup_stats"),
                         ("trend", "points", "usage_trend"), ("tera", None, "tera_stats")):
        fs = m["datasets"][ds]
        rows = [r for f in fs for r in json.loads((args.out / f["path"]).read_text(encoding="utf-8"))["rows"]]
        items = rows if key is None else [i for r in rows for i in r[key]]
        key = key or "species rows"
        print(f"{ds}: {len(fs)} files, {sum(f['rows'] for f in fs):,} species rows, "
              f"{sum(f['bytes'] for f in fs) / 1024:,.1f} KiB, largest {max((f['bytes'] for f in fs), default=0) / 1024:,.1f} KiB"
              + ("" if fs else f" (table not found in --agg: run {job})"))
        print(f"  checks: {len(items):,} {key}, every n >= {MIN_N}: {all(i['n'] >= MIN_N for i in items)}; "
              f"one file per regulation x band: {len({(f['regulation'], f['rating_band']) for f in fs}) == len(fs)}")
    tails = {}
    for f in m["datasets"]["trend"]:
        for mo in json.loads((args.out / f["path"]).read_text(encoding="utf-8"))["months"]:
            tails.setdefault((f["regulation"], mo["month"]), set()).add(mo["tail"])
    print(f"  trend: {sum(True in v for v in tails.values())} tail regulation-months; "
          f"tail identical in every band: {all(len(v) == 1 for v in tails.values())}")
    print(f"checks: manifest sizes match files: {all(on_disk[f['path']] == f['bytes'] for f in files)}; "
          f"every file < 100 MB: {all(v < 100 * 2**20 for v in on_disk.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
