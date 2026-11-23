import numpy as np
from numpy import core
import pandas as pd
import pytest

from python.analytics import eda_report as eda

REG = "gen9vgc2025regi"


def _usage(rows, band="all", pb=1000):
    return pd.DataFrame([{"regulation": REG, "rating_band": band, "species_id": i, "species": name, "form": None, "poke_id": None,
                          "form_basis": "listed", "appearances": a, "wins": w, "sent_out": a, "leads": 0, "player_battles": pb}
                         for i, (name, a, w) in enumerate(rows, start=1)])


def test_concentration_effective_species_and_top_usage():
    c = eda.concentration(_usage([("A", 500, 250), ("B", 500, 250)]))
    r = c.iloc[0]
    assert r["effective_species"] == 2.0 and r["top1_usage_%"] == 50.0 and r["species_over_5%"] == 2
    assert eda.concentration(_usage([("A", 900, 450), ("B", 100, 50)])).iloc[0]["effective_species"] < 2.0   # more concentrated


def _monthly(usage_by_month, tail=()):
    rows = []
    for month, shares in usage_by_month.items():
        for sid, share in shares.items():
            rows.append({"regulation": REG, "month": month, "species_id": sid, "appearances": int(share * 100000),
                         "usage_share": share, "player_battles": 100000, "tail": month in tail})
    return pd.DataFrame(rows)


def test_stability_is_one_for_a_steady_ranking_and_negative_for_a_reversed_one():
    steady = {m: {1: .5, 2: .4, 3: .3, 4: .2, 5: .1} for m in ("2025-01", "2025-02", "2025-03")}
    assert eda.stability(_monthly(steady)).iloc[0]["mean_rank_corr"] == 1.0
    flipped = {"2025-01": {1: .5, 2: .4, 3: .3}, "2025-02": {1: .1, 2: .2, 3: .3}}
    assert eda.stability(_monthly(flipped)).iloc[0]["mean_rank_corr"] == -1.0


def test_stability_ignores_tail_months():
    data = {"2025-01": {1: .5, 2: .4, 3: .3}, "2025-02": {1: .5, 2: .4, 3: .3}, "2025-03": {1: .1, 2: .2, 3: .3}}
    r = eda.stability(_monthly(data, tail=("2025-03",))).iloc[0]
    assert r["months"] == 2 and r["mean_rank_corr"] == 1.0


def test_band_shift_reports_percentage_points_between_bands():
    low = _usage([("Calyrex", 2500, 1250), ("Koraidon", 5000, 2500)], band="below_1200", pb=10000)
    high = _usage([("Calyrex", 6000, 3100), ("Koraidon", 2500, 1200)], band="1500_plus", pb=10000)
    s = eda.band_shift(pd.concat([low, high]), REG, n=1).set_index("species")
    assert s.loc["Calyrex", "shift_pp"] == 35.0 and s.loc["Koraidon", "shift_pp"] == -25.0


def test_popularity_vs_success_detects_a_monotonic_relation():
    rows = [(f"S{i}", 2000 + 500 * i, int((2000 + 500 * i) * (0.45 + 0.01 * i))) for i in range(12)]
    assert eda.popularity_vs_success(_usage(rows, pb=100000)).iloc[0]["spearman_usage_vs_win_delta"] == 1.0
    assert eda.popularity_vs_success(_usage(rows[:5], pb=100000)).empty          # too few species to say anything


def test_tera_profile_measures_how_predictable_the_type_is():
    summary = pd.DataFrame({"regulation": [REG] * 2, "rating_band": [eda.ALL] * 2, "species_id": [1, 2],
                            "sent_out": [10000, 10000], "tera_events": [6000, 5000]})
    types = pd.DataFrame({"regulation": [REG] * 3, "rating_band": [eda.ALL] * 3, "species_id": [1, 1, 2],
                          "tera_type": ["Fire", "Water", "Fairy"], "type_share": [0.9, 0.1, 0.4]})
    r = eda.tera_profile(summary, types).iloc[0]
    assert r["tera_per_sent_out_%"] == 55.0 and r["species_analysed"] == 2
    assert r["median_top_type_share_%"] == 65.0 and r["share_with_top_type_>=50%"] == 50.0
    assert eda.tera_profile(summary.assign(tera_events=0), types).empty        # a regulation without Tera is left out


def test_top_pairs_sorts_by_lift_and_applies_min_teams():
    p = pd.DataFrame({"regulation": REG, "rating_band": eda.ALL, "species_a": ["A", "A", "B"], "species_b": ["B", "C", "C"],
                      "teams_both": [9000, 100, 7000], "lift": [1.5, 9.0, 2.5]})
    assert list(eda.top_pairs(p, REG)["species_b"]) == ["C", "B"] and list(eda.top_pairs(p, REG)["lift"]) == [2.5, 1.5]


def test_matchup_spread_counts_pairs_far_from_expectation():
    m = pd.DataFrame({"regulation": REG, "rating_band": eda.ALL, "battles": [3000] * 4, "win_rate_vs_expected": [0.01, -0.02, 0.03, -0.05],
                      "z_vs_expected": [1.0, -2.0, 3.0, -5.0]})
    r = eda.matchup_spread(m).iloc[0]
    assert (r["pairs"], r["share_abs_z_gt_4_%"], r["median_abs_pp"]) == (4, 25.0, 2.5)


def test_markdown_table_formats_numbers_and_blanks():
    t = eda.md_table(pd.DataFrame({"a": [1234, 2], "b": [1.5, np.nan]}))
    assert "| 1,234 | 1.5 |" in t and "| 2 |  |" in t
    assert eda.md_table(pd.DataFrame()) == "_(no data)_\n"


def test_report_is_generated_from_the_aggregate_tables(tmp_path):
    from python.analytics import dim_tables, matchup_stats, partner_stats, pokemon_usage, tera_stats, usage_trend
    from python.test.test_partner_stats import TEAMS
    from python.test.test_pokemon_usage import _write
    from python.test.test_tera_stats import TERA

    out, name_map = _write(tmp_path)
    pd.DataFrame(TERA, columns=["battle_id", "username", "species", "tera_type"]).to_parquet(out / "battle_tera.parquet")
    nm = pd.concat([name_map, pd.DataFrame([("Rillaboom", 812, "rillaboom", 812, "exact", "known")], columns=name_map.columns)], ignore_index=True)
    map_csv, agg = tmp_path / "map.csv", tmp_path / "agg"
    nm.to_csv(map_csv, index=False)
    common = ["--output-dir", str(out), "--map", str(map_csv), "--out", str(agg)]
    pokemon_usage.main(common)                                   # these three need the full team-slot columns
    tera_stats.main(common + ["--usage", str(agg / "pokemon_usage_stats.parquet")])
    usage_trend.main(common)
    dim_tables.main(common)
    pd.DataFrame(TEAMS, columns=["battle_id", "player_side", "pokemon_name"]).to_parquet(out / "battle_team_slot.parquet")
    partner_stats.main(common + ["--min-support", "1"])          # pairs and matchups only read the team composition
    matchup_stats.main(common + ["--min-support", "1"])

    text = eda.build_report(agg, tmp_path / "docs", min_player_battles=1)
    assert (tmp_path / "docs" / "EDA_FINDINGS.md").read_text(encoding="utf-8") == text
    assert "## 1. How concentrated" in text and "Reg G 2024" in text            # label from dim_regulation
    assert (tmp_path / "docs" / "img" / "concentration.png").exists()
    with pytest.raises(FileNotFoundError):
        eda.build_report(tmp_path / "empty", tmp_path / "docs2")


def _two_bands(per_band):
    """per_band: {band: [(species, appearances, win_delta)]} -> usage rows with wins = appearances * (baseline + delta)."""
    frames = []
    for band, rows in per_band.items():
        pb = 100000
        base = {"below_1200": 0.45, "1500_plus": 0.55}[band]
        frames.append(_usage([(n, a, int(a * (base + d))) for n, a, d in rows], band=band, pb=pb))
    return pd.concat(frames, ignore_index=True)


def test_a_rating_driven_correlation_disappears_inside_each_band():
    # 12 species: the popular ones are used mostly by strong players (higher baseline), but inside a band the win delta
    # alternates +/- whatever the usage is
    sp = [f"S{i}" for i in range(12)]
    alt = [0.01 if i % 2 == 0 else -0.01 for i in range(12)]
    low = [(n, 3000 - 100 * i, alt[i]) for i, n in enumerate(sp)]                    # weak players: popular = common
    high = [(n, 600 + 700 * (11 - i) // 1, alt[i]) for i, n in enumerate(sp)]       # strong players use the popular species more
    usage = _two_bands({"below_1200": low, "1500_plus": high})
    wide = eda.popularity_by_band(usage, min_teams_band=100).iloc[0]
    assert abs(wide["below_1200"]) < 0.35 and abs(wide["1500_plus"]) < 0.35
    both = pd.concat([usage.assign(rating_band=eda.ALL)]).groupby(
        ["regulation", "rating_band", "species_id", "species", "form", "poke_id", "form_basis"], dropna=False, as_index=False).sum()
    both["player_battles"] = 200000
    assert eda.popularity_vs_success(both, min_teams=100).iloc[0]["spearman_usage_vs_win_delta"] > 0.5   # the mixture looks like a relation

def test_popularity_by_band_uses_one_species_set_in_every_band():
    # weak players also use 10 rare species that lose; strong players do not. Over the whole weak-band list that tail makes
    # popularity look like success; on the fixed set (species with enough teams at 1500+) it does not.
    sp = [f"S{i}" for i in range(12)]
    alt = [0.01 if i % 2 == 0 else -0.01 for i in range(12)]
    core = [(n, 3000 - 100 * i, alt[i]) for i, n in enumerate(sp)]
    tail = [(f"T{i}", 30, -0.05) for i in range(10)]
    usage = _two_bands({"below_1200": core + tail, "1500_plus": core})
    assert eda.popularity_vs_success(usage, min_teams=1, band="below_1200").iloc[0]["spearman_usage_vs_win_delta"] > 0.5
    r = eda.popularity_by_band(usage, min_teams_band=100).iloc[0]
    assert r["species"] == 12 and abs(r["below_1200"]) < 0.35 and abs(r["1500_plus"]) < 0.35
    assert np.isnan(r["1200_1399"])                                                   # band absent from the data: left empty
    assert eda.popularity_by_band(usage, min_teams_band=100000).empty                  # too few species at the reference band

def test_tiny_regulations_are_left_out_of_the_report(tmp_path):
    from python.analytics import dim_tables, pokemon_usage
    from python.test.test_pokemon_usage import _write
    out, name_map = _write(tmp_path)
    map_csv, agg = tmp_path / "map.csv", tmp_path / "agg"
    name_map.to_csv(map_csv, index=False)
    common = ["--output-dir", str(out), "--map", str(map_csv), "--out", str(agg)]
    pokemon_usage.main(common)
    dim_tables.main(common)
    text = eda.build_report(agg, tmp_path / "docs", plots=False)            # 4 player-battles: below the default 50,000
    assert "No regulation has at least 50,000 player-battles" in text and "gen9vgc2024regg (4)" in text
    kept = eda.build_report(agg, tmp_path / "docs2", plots=False, min_player_battles=1)
    assert "Left out" not in kept and "Reg G 2024" in kept