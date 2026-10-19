"""EDA on the aggregate tables: findings with their numbers, charts, and a generated report.

    python -m python.analytics.eda_report --agg data/aggregates --out docs

Reads the Parquet / CSV files written by the aggregate modules and writes docs/EDA_FINDINGS.md and docs/img/*.png.
Every statement in the report is generated from a table, so numbers and text cannot drift apart. Definitions and
caveats: METRICS.md. All figures are descriptive; none of them is a causal claim.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ALL = "all"


# ---------------------------------------------------------------- analyses (pure functions on aggregate tables)
def _species_level(usage: pd.DataFrame, band: str = ALL) -> pd.DataFrame:
    """Usage rows summed over forms: regulation x species."""
    u = usage[usage["rating_band"] == band]
    g = u.groupby(["regulation", "species_id", "species"], as_index=False)[["appearances", "wins", "sent_out", "leads"]].sum()
    pb = u.drop_duplicates("regulation").set_index("regulation")["player_battles"]
    g["player_battles"] = g["regulation"].map(pb)
    g["usage"] = g["appearances"] / g["player_battles"]
    return g


def concentration(usage: pd.DataFrame) -> pd.DataFrame:
    """Meta concentration per regulation: top species, mean usage of the top 5, species above 5%, effective species."""
    rows = []
    for reg, g in _species_level(usage).groupby("regulation"):
        g = g.sort_values("usage", ascending=False)
        p = g["appearances"] / g["appearances"].sum()                  # share of team slots
        rows.append({"regulation": reg, "top_species": g["species"].iloc[0], "top1_usage_%": round(100 * g["usage"].iloc[0], 1),
                     "top5_mean_usage_%": round(100 * g["usage"].head(5).mean(), 1),
                     "species_over_5%": int((g["usage"] >= 0.05).sum()), "effective_species": round(float(1 / (p ** 2).sum()), 1)})
    return pd.DataFrame(rows, columns=["regulation", "top_species", "top1_usage_%", "top5_mean_usage_%", "species_over_5%", "effective_species"])


def stability(monthly: pd.DataFrame, top: int = 30, min_player_battles: int = 20000) -> pd.DataFrame:
    """Mean rank correlation (Spearman) of species usage between consecutive months, non-tail months only."""
    rows = []
    for reg, g in monthly.groupby("regulation"):
        g = g[(~g["tail"].astype(bool)) & (g["player_battles"] >= min_player_battles) & (g["month"] != "unknown")]
        wide = g.pivot_table(index="species_id", columns="month", values="usage_share", fill_value=0.0)
        if wide.shape[1] < 2:
            continue
        keep = g.groupby("species_id")["appearances"].sum().nlargest(top).index
        wide = wide.loc[wide.index.intersection(keep)]
        months = sorted(wide.columns)
        corr = [wide[a].corr(wide[b], method="spearman") for a, b in zip(months[:-1], months[1:])]
        rows.append({"regulation": reg, "months": len(months), "mean_rank_corr": round(float(np.nanmean(corr)), 3),
                     "min_rank_corr": round(float(np.nanmin(corr)), 3)})
    return pd.DataFrame(rows, columns=["regulation", "months", "mean_rank_corr", "min_rank_corr"])


def band_shift(usage: pd.DataFrame, regulation: str, low: str = "below_1200", high: str = "1500_plus",
               min_teams: int = 2000, n: int = 8) -> pd.DataFrame:
    """Usage in the high band minus usage in the low band (percentage points), for species seen often in both."""
    lo, hi = _species_level(usage, low), _species_level(usage, high)
    m = lo[lo["regulation"] == regulation].merge(hi[hi["regulation"] == regulation], on=["species_id", "species"], suffixes=("_low", "_high"))
    m = m[(m["appearances_low"] >= min_teams) & (m["appearances_high"] >= min_teams)]
    m["shift_pp"] = (100 * (m["usage_high"] - m["usage_low"])).round(1)
    m = m.sort_values("shift_pp")
    cols = ["species", "usage_low", "usage_high", "shift_pp"]
    return pd.concat([m.head(n)[cols], m.tail(n)[cols]]).assign(usage_low=lambda d: (100 * d["usage_low"]).round(1),
                                                                 usage_high=lambda d: (100 * d["usage_high"]).round(1)).reset_index(drop=True)


def popularity_vs_success(usage: pd.DataFrame, min_teams: int = 2000, band: str = ALL) -> pd.DataFrame:
    """Rank correlation between usage and win rate relative to the baseline of the same regulation and rating band."""
    rows = []
    for reg, g in _species_level(usage, band).groupby("regulation"):
        base = g["wins"].sum() / g["appearances"].sum()
        g = g[g["appearances"] >= min_teams].assign(delta=lambda d: d["wins"] / d["appearances"] - base)
        if len(g) >= 10:
            rows.append({"regulation": reg, "species": len(g), "spearman_usage_vs_win_delta": round(float(g["usage"].corr(g["delta"], method="spearman")), 2)})
    return pd.DataFrame(rows, columns=["regulation", "species", "spearman_usage_vs_win_delta"])


def popularity_by_band(usage: pd.DataFrame, min_teams_band: int = 500, reference_band: str = "1500_plus", min_species: int = 10) -> pd.DataFrame:
    """The same correlation per rating band, on ONE species set per regulation: the species with at least `min_teams_band` teams in
    `reference_band`. Each band uses its own baseline, but the species list is identical in every band, so a difference between bands is
    not a difference in which species are counted (weak bands also contain a long tail of rarely used species that strong bands do not).
    `species` is the size of that set. Regulations with fewer than `min_species` species are left out."""
    bands = [ALL, "below_1200", "1200_1399", "1400_1499", "1500_plus"]
    levels = {b: _species_level(usage, b) for b in dict.fromkeys(bands + [reference_band])}
    rows = []
    for reg, ref in levels[reference_band].groupby("regulation"):
        keep = set(ref.loc[ref["appearances"] >= min_teams_band, "species_id"])
        if len(keep) < min_species:
            continue
        row = {"regulation": reg, "species": len(keep)}
        for b in bands:
            whole = levels[b][levels[b]["regulation"] == reg]
            g = whole[whole["species_id"].isin(keep)]
            if len(g) < min_species:
                row[b] = np.nan
                continue
            g = g.assign(delta=g["wins"] / g["appearances"] - whole["wins"].sum() / whole["appearances"].sum())
            row[b] = round(float(g["usage"].corr(g["delta"], method="spearman")), 2)
        rows.append(row)
    return pd.DataFrame(rows, columns=["regulation", "species"] + bands)


def tera_profile(summary: pd.DataFrame, types: pd.DataFrame, min_events: int = 5000) -> pd.DataFrame:
    """Per regulation with Tera: adoption, and how predictable the Tera type of a species is (share of its most used type)."""
    s, t = summary[summary["rating_band"] == ALL], types[types["rating_band"] == ALL]
    rows = []
    for reg, g in s.groupby("regulation"):
        if g["tera_events"].sum() == 0:
            continue
        big = g[g["tera_events"] >= min_events]
        top_share = t[(t["regulation"] == reg) & t["species_id"].isin(big["species_id"])].groupby("species_id")["type_share"].max()
        rows.append({"regulation": reg, "tera_per_sent_out_%": round(100 * g["tera_events"].sum() / g["sent_out"].sum(), 1),
                     "species_analysed": len(top_share), "median_top_type_share_%": round(100 * float(top_share.median()), 1) if len(top_share) else np.nan,
                     "share_with_top_type_>=50%": round(100 * float((top_share >= 0.5).mean()), 1) if len(top_share) else np.nan})
    return pd.DataFrame(rows, columns=["regulation", "tera_per_sent_out_%", "species_analysed", "median_top_type_share_%", "share_with_top_type_>=50%"])


def top_pairs(partner: pd.DataFrame, regulation: str, min_teams: int = 5000, n: int = 10) -> pd.DataFrame:
    p = partner[(partner["regulation"] == regulation) & (partner["rating_band"] == ALL) & (partner["teams_both"] >= min_teams)]
    return p.sort_values("lift", ascending=False).head(n)[["species_a", "species_b", "teams_both", "lift"]].round({"lift": 2}).reset_index(drop=True)


def matchup_spread(matchup: pd.DataFrame, min_battles: int = 2000) -> pd.DataFrame:
    """How far team-level matchups deviate from what the two teams' overall strength predicts."""
    rows = []
    for reg, g in matchup[(matchup["rating_band"] == ALL) & (matchup["battles"] >= min_battles)].groupby("regulation"):
        dev = (100 * g["win_rate_vs_expected"]).abs()
        rows.append({"regulation": reg, "pairs": len(g), "median_abs_pp": round(float(dev.median()), 2),
                     "p95_abs_pp": round(float(dev.quantile(0.95)), 2), "share_abs_z_gt_4_%": round(100 * float((g["z_vs_expected"].abs() > 4).mean()), 1)})
    return pd.DataFrame(rows, columns=["regulation", "pairs", "median_abs_pp", "p95_abs_pp", "share_abs_z_gt_4_%"])


# ---------------------------------------------------------------- report
def md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_(no data)_\n"
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join("" if (isinstance(v, float) and np.isnan(v)) else (f"{v:,}" if isinstance(v, (int, np.integer)) else str(v)) for v in row) + " |")
    return "\n".join(lines) + "\n"


def _ordered(df: pd.DataFrame, order: list[str], label: dict) -> pd.DataFrame:
    """Rows in regulation order (oldest first) with readable regulation labels."""
    if df.empty:
        return df
    rank = {r: i for i, r in enumerate(order)}
    df = df.assign(_o=df["regulation"].map(rank).fillna(len(rank))).sort_values("_o", kind="stable").drop(columns="_o")
    return df.assign(regulation=df["regulation"].map(lambda r: label.get(r, r))).reset_index(drop=True)


def _read(agg: Path, name: str) -> pd.DataFrame | None:
    for ext, reader in ((".parquet", pd.read_parquet), (".csv", pd.read_csv)):
        if (agg / f"{name}{ext}").exists():
            return reader(agg / f"{name}{ext}")
    return None


read_table = _read      # public name for notebooks


def _save(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    import matplotlib.pyplot as plt
    plt.close(fig)


def build_report(agg: Path, out: Path, plots: bool = True, min_player_battles: int = 50_000) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    usage, monthly = _read(agg, "pokemon_usage_stats"), _read(agg, "pokemon_usage_monthly")
    tera_s, tera_t = _read(agg, "pokemon_tera_summary"), _read(agg, "pokemon_tera_types")
    partner, matchup, dim = _read(agg, "pokemon_partner_stats"), _read(agg, "pokemon_matchup_stats"), _read(agg, "dim_regulation")
    if usage is None:
        raise FileNotFoundError(f"pokemon_usage_stats not found in {agg}; run python -m python.analytics.pokemon_usage first")
    size = usage[usage["rating_band"] == ALL].drop_duplicates("regulation").set_index("regulation")["player_battles"]
    left_out = size[size < min_player_battles]
    keep = set(size[size >= min_player_battles].index)
    usage = usage[usage["regulation"].isin(keep)]
    monthly, tera_s, tera_t, partner, matchup = [None if d is None else d[d["regulation"].isin(keep)] for d in (monthly, tera_s, tera_t, partner, matchup)]
    if usage.empty:
        text = ("# EDA findings\n\nNo regulation has at least " f"{min_player_battles:,} player-battles; left out: "
                + ", ".join(f"{r} ({int(n):,})" for r, n in left_out.items()) + ".\n")
        out.mkdir(parents=True, exist_ok=True)
        (out / "EDA_FINDINGS.md").write_text(text, encoding="utf-8")
        return text
    order = list(dim.sort_values("sort_order")["regulation"]) if dim is not None else sorted(usage["regulation"].unique())
    label = dict(zip(dim["regulation"], dim["label"])) if dim is not None else {}
    biggest = usage[usage["rating_band"] == ALL].drop_duplicates("regulation").sort_values("player_battles").iloc[-1]["regulation"]
    img = out / "img"
    md = ["# EDA findings", "",
          "Generated by `python -m python.analytics.eda_report` from the aggregate tables. Every number below is computed, "
          "descriptive and population-bound: completed VGC battles of the regulation shown (see [`METRICS.md`](../METRICS.md)). "
          "Nothing here is a causal claim. The narrative lives in [`EDA_INSIGHTS.md`](EDA_INSIGHTS.md).", ""]
    if len(left_out):
        md += ["Left out because they have fewer than " f"{min_player_battles:,} player-battles: "
               + ", ".join(f"{label.get(r, r)} ({int(n):,})" for r, n in left_out.items()) + ".", ""]

    conc = _ordered(concentration(usage), order, label)
    md += ["## 1. How concentrated is each regulation's meta?", "",
           "`effective_species` is 1 / sum(p²) over each species' share of team slots: the number of equally used species that would "
           "give the same concentration (higher = more diverse).", "", md_table(conc)]
    if plots and len(conc):
        fig, ax = plt.subplots(figsize=(8, 3.6))
        ax.bar(conc["regulation"], conc["effective_species"], color="#4c78a8")
        ax.set_ylabel("effective species"); ax.set_title("Meta diversity by regulation"); plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
        _save(fig, img / "concentration.png"); md += ["![](img/concentration.png)", ""]

    if monthly is not None:
        st = _ordered(stability(monthly), order, label)
        md += ["## 2. How fast does the meta settle?", "",
               "Spearman rank correlation of species usage between consecutive months (top 30 species, tail months excluded). "
               "Close to 1 means the ranking barely moves.", "", md_table(st)]

    bands = set(usage["rating_band"])
    if {"below_1200", "1500_plus"} <= bands:
        sh = band_shift(usage, biggest)
        md += [f"## 3. What do strong players pick differently? ({label.get(biggest, biggest)})", "",
               "Usage among players rated 1500+ minus usage among players below 1200, in percentage points "
               "(species with at least 2,000 teams in both bands).", "", md_table(sh)]
        if plots and len(sh):
            fig, ax = plt.subplots(figsize=(7, 4.5))
            ax.barh(sh["species"], sh["shift_pp"], color=np.where(sh["shift_pp"] >= 0, "#59a14f", "#e15759"))
            ax.set_xlabel("usage 1500+ minus usage below 1200 (pp)"); ax.set_title(f"Rating-band shift, {label.get(biggest, biggest)}")
            _save(fig, img / "band_shift.png"); md += ["![](img/band_shift.png)", ""]

    pv = _ordered(popularity_vs_success(usage), order, label)
    md += ["## 4. Does popularity predict win rate?", "",
           "Rank correlation between a species' usage and its win rate minus the regulation baseline (species with at least 2,000 teams). "
           "A value near 0 means popular species are not systematically better or worse.", "", md_table(pv),
           "Strong players pick popular species and also win more, so part of this could be a rating effect. A second view computes the same "
           "correlation inside each rating band (baseline of that band) on one fixed species set per regulation: the species with at least 500 teams "
           "among players rated 1500+ (`species` counts them). The species list is then the same in every band, so differences between bands "
           "are not caused by which species are counted; the `all` column uses the same set:", "",
           md_table(_ordered(popularity_by_band(usage), order, label))]

    if tera_s is not None and tera_t is not None:
        tp = _ordered(tera_profile(tera_s, tera_t), order, label)
        md += ["## 5. How predictable is the Tera type?", "",
               "For species with at least 5,000 Terastallizations: the share taken by their most used Tera type.", "", md_table(tp)]

    if partner is not None:
        tpairs = top_pairs(partner, biggest)
        md += [f"## 6. Teammates seen together far more than chance ({label.get(biggest, biggest)})", "",
               "Highest lift among pairs on at least 5,000 teams. Lift is co-occurrence, not synergy.", "", md_table(tpairs)]

    if matchup is not None:
        ms = _ordered(matchup_spread(matchup), order, label)
        md += ["## 7. Are there team-level counters?", "",
               "Distance (percentage points) between the observed win rate of a team with species A against a team with species B and what the "
               "two teams' overall win rates predict (pairs with at least 2,000 battles). Small values mean team-level matchups add little beyond general strength.", "",
               md_table(ms)]
        if plots and len(matchup):
            m = matchup[(matchup["rating_band"] == ALL) & (matchup["battles"] >= 2000)]
            fig, ax = plt.subplots(figsize=(7, 3.6))
            ax.hist(100 * m["win_rate_vs_expected"], bins=60, color="#4c78a8")
            ax.set_xlabel("observed minus expected win rate (pp)"); ax.set_ylabel("species pairs"); ax.set_title("Team-level matchups vs expectation")
            _save(fig, img / "matchup_spread.png"); md += ["![](img/matchup_spread.png)", ""]

    text = "\n".join(md)
    out.mkdir(parents=True, exist_ok=True)
    (out / "EDA_FINDINGS.md").write_text(text, encoding="utf-8")
    return text


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agg", type=Path, default=Path("data/aggregates"))
    ap.add_argument("--out", type=Path, default=Path("docs"))
    ap.add_argument("--no-plots", action="store_true")
    ap.add_argument("--min-player-battles", type=int, default=50_000, help="leave out regulations smaller than this")
    args = ap.parse_args(argv)
    text = build_report(args.agg, args.out, plots=not args.no_plots, min_player_battles=args.min_player_battles)
    print(text)
    print(f"\nWrote {args.out / 'EDA_FINDINGS.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())