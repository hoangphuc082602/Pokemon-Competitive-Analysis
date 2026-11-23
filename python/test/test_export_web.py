"""Seam 1: aggregate directory in -> static web data out (python.analytics.export_web)."""
import json

import pandas as pd
import pytest

from python.analytics.export_web import ExportError, export

REG = "gen9vgc2024regg"


def _write(tmp_path, extra_cols=None, extra_rows=()):
    """Synthetic aggregates as written by pokemon_usage (form grain, 'all' band rows included).
    The export reads aggregates, not event tables, so this mirrors test_pokemon_usage._write at the next layer:
    counts chosen so that 'all' differs from the sum of bands and n crosses the threshold."""
    agg = tmp_path / "agg"
    agg.mkdir()
    rows = [  # band, species, species_id, poke_id, form, form_basis, appearances, wins, leads
        ("all", "Urshifu", 892, 10191, "urshifu-rapid-strike", "observed", 150, 90, 60),
        ("all", "Urshifu", 892, None, None, "unobserved", 120, 50, 0),     # masked, never sent out: own row
        ("all", "Incineroar", 727, 727, "incineroar", "listed", 300, 150, 150),
        ("all", "Calyrex", 898, 10193, "calyrex-shadow", "listed", 200, 120, 50),
        ("all", "Calyrex", 898, 10194, "calyrex-ice", "listed", 99, 60, 0),  # species 299, this form < 100
        ("all", "Arceus", 493, None, None, "species_only", 100, 50, 0),     # e.g. Arceus-Fire: not in master data
        ("all", "Rare", 1, 1, "rare", "listed", 99, 99, 0),                 # n < 100: hidden, but in the baseline
        ("1500_plus", "Incineroar", 727, 727, "incineroar", "listed", 120, 72, 60),
        ("1500_plus", "Urshifu", 892, 10191, "urshifu-rapid-strike", "observed", 100, 40, 10),
        ("1500_plus", "Rare", 1, 1, "rare", "listed", 20, 0, 0),
        # 'all' deliberately differs from the sum of bands: the export must take 'all' rows as given
        *extra_rows,
    ]
    df = pd.DataFrame(rows, columns=["rating_band", "species", "species_id", "poke_id", "form", "form_basis",
                                     "appearances", "wins", "leads"])
    df["regulation"] = REG
    df["sent_out"] = df["appearances"]
    df["player_battles"] = df["rating_band"].map({"all": 1000, "1500_plus": 400})
    for col, val in (extra_cols or {}).items():
        df[col] = val
    df.to_parquet(agg / "pokemon_usage_stats.parquet", index=False)
    pd.DataFrame({"regulation": [REG, REG], "rating_band": ["all", "1500_plus"],
                  "battles": [500, None], "player_battles": [1000, 400]}).to_csv(agg / "regulation_totals.csv", index=False)
    return agg


@pytest.fixture
def exported(tmp_path):
    out = tmp_path / "web"
    manifest = export(_write(tmp_path), out, batch_size=2)     # tiny batches: exercises the streaming path
    return out, manifest


def _file(out, manifest, band):
    entry = next(f for f in manifest["datasets"]["team_usage"] if f["rating_band"] == band)
    return entry, json.loads((out / entry["path"]).read_text(encoding="utf-8"))


def _rows(out, manifest, band):
    return {r["label"]: r for r in _file(out, manifest, band)[1]["rows"]}


def test_forms_below_100_player_battles_are_not_exported(exported):
    rows = _rows(*exported, "all")
    assert set(rows) == {"Urshifu-Rapid-Strike (seen in battle)", "Urshifu (form unknown)", "Incineroar", "Calyrex-Shadow",
                         "Arceus (form not in master data)"}                  # Calyrex-Ice 99 < 100 though species 299
    assert all(r["n"] >= 100 for r in rows.values())


def test_a_masked_family_never_sent_out_is_its_own_row_and_never_guessed(exported):
    rows = _rows(*exported, "all")
    unknown = rows["Urshifu (form unknown)"]
    assert (unknown["species"], unknown["poke_id"], unknown["form"], unknown["form_basis"]) == \
           ("Urshifu", None, None, "unobserved")
    assert (unknown["n"], rows["Urshifu-Rapid-Strike (seen in battle)"]["n"]) == (120, 150)   # unobserved share 120 / 270
    assert rows["Urshifu-Rapid-Strike (seen in battle)"]["form_basis"] == "observed"


def test_a_form_missing_from_the_master_data_stays_at_species_level(exported):
    arceus = _rows(*exported, "all")["Arceus (form not in master data)"]
    assert (arceus["species_id"], arceus["poke_id"], arceus["form"], arceus["form_basis"], arceus["n"]) == \
           (493, None, None, "species_only", 100)


def test_listed_forms_of_one_species_are_separate_rows(exported):
    shadow = _rows(*exported, "all")["Calyrex-Shadow"]
    assert (shadow["species"], shadow["form"], shadow["poke_id"], shadow["form_basis"]) == \
           ("Calyrex", "calyrex-shadow", 10193, "listed")
    assert (shadow["n"], shadow["win_rate"], shadow["lead_rate"]) == (200, 0.6, 0.25)   # not the species total 299


def test_win_rate_delta_is_against_the_bands_own_baseline(exported):
    out, manifest = exported
    _, top = _file(out, manifest, "1500_plus")
    assert top["baseline_win_rate"] == pytest.approx(112 / 240, abs=1e-5)  # all species of the band, Rare included
    inc = _rows(out, manifest, "1500_plus")["Incineroar"]
    assert inc["win_rate_delta"] == pytest.approx(0.6 - 112 / 240, abs=1e-5)
    _, all_ = _file(out, manifest, "all")
    assert all_["baseline_win_rate"] == pytest.approx(619 / 1068, abs=1e-5)  # every form row, hidden ones included
    assert _rows(out, manifest, "all")["Incineroar"]["win_rate_delta"] == pytest.approx(0.5 - 619 / 1068, abs=1e-5)


def test_rows_carry_n_and_a_wilson_interval(exported):
    inc = _rows(*exported, "all")["Incineroar"]
    assert inc["win_ci_low"] < 0.5 < inc["win_ci_high"]
    assert inc["win_ci_low"] == pytest.approx(0.4436, abs=1e-3)           # Wilson 150/300
    assert inc["lead_rate"] == 0.5 and inc["usage_share"] == 0.3


def test_all_band_is_its_own_file_taken_as_given_never_a_sum_of_bands(exported):
    out, manifest = exported
    assert {f["rating_band"] for f in manifest["datasets"]["team_usage"]} == {"all", "1500_plus"}
    assert _rows(out, manifest, "all")["Incineroar"]["n"] == 300           # bands would sum to 120
    assert _file(out, manifest, "all")[1]["player_battles"] == 1000


@pytest.mark.parametrize("col", ["username", "battle_id", "replay_id", "p1_user"])
def test_a_forbidden_input_column_makes_the_export_fail_without_writing(tmp_path, col):
    agg, out = _write(tmp_path, {col: "x"}), tmp_path / "web"
    with pytest.raises(ExportError, match=col):
        export(agg, out)
    assert not out.exists()


def test_exported_files_hold_only_allow_listed_keys(exported):
    out, manifest = exported
    for f in manifest["datasets"]["team_usage"]:
        data = json.loads((out / f["path"]).read_text(encoding="utf-8"))
        assert list(data) == ["regulation", "rating_band", "player_battles", "baseline_win_rate", "min_n", "rows"]
        for r in data["rows"]:
            assert list(r) == ["species_id", "species", "poke_id", "form", "form_basis", "label", "n", "usage_share", "win_rate", "win_ci_low", "win_ci_high",
                               "win_rate_delta", "lead_rate"]


def test_manifest_counts_and_sizes_match_the_files(exported):
    out, manifest = exported
    assert manifest["schema_version"] == 4 and manifest["min_n"] == 100
    on_disk = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk == manifest
    for f in manifest["datasets"]["team_usage"]:
        path = out / f["path"]
        assert f["bytes"] == path.stat().st_size
        assert f["rows"] == len(json.loads(path.read_text(encoding="utf-8"))["rows"])
    assert manifest["regulations"] == [{"id": REG, "battles": 500, "player_battles": 1000, "bands": ["all", "1500_plus"]}]
    assert manifest["bands"] == ["all", "1500_plus"] and manifest["totals"] == {"battles": 500, "player_battles": 1000}


def test_csv_aggregates_give_the_same_export(tmp_path):
    agg = _write(tmp_path)
    pd.read_parquet(agg / "pokemon_usage_stats.parquet").to_csv(agg / "pokemon_usage_stats.csv", index=False)
    a = export(agg, tmp_path / "a", snapshot_date="2026-01-01")
    (agg / "pokemon_usage_stats.parquet").unlink()
    b = export(agg, tmp_path / "b", snapshot_date="2026-01-01", batch_size=3)
    assert a == b
    assert (tmp_path / "a" / a["datasets"]["team_usage"][0]["path"]).read_text() == \
           (tmp_path / "b" / b["datasets"]["team_usage"][0]["path"]).read_text()


def test_files_of_an_earlier_export_are_removed(tmp_path):
    out = tmp_path / "web"
    stale = out / "team_usage" / "gen9vgc2023regd__all.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}", encoding="utf-8")
    manifest = export(_write(tmp_path), out)
    assert not stale.exists()
    assert sorted(p.name for p in (out / "team_usage").iterdir()) == \
           sorted(f["path"].split("/")[1] for f in manifest["datasets"]["team_usage"])


def test_species_form_mapping_lists_each_exported_form_once(exported):
    out, manifest = exported
    entry = manifest["datasets"]["species_forms"]
    data = json.loads((out / entry["path"]).read_text(encoding="utf-8"))
    assert data == [{"species": "Calyrex", "form": "calyrex-shadow"},          # Calyrex-Ice is in no exported file
                    {"species": "Incineroar", "form": "incineroar"},
                    {"species": "Urshifu", "form": "urshifu-rapid-strike"}]   # in two bands, listed once
    assert (entry["rows"], entry["bytes"]) == (3, (out / entry["path"]).stat().st_size)


def test_a_form_both_listed_and_revealed_in_battle_keeps_two_distinguishable_rows(tmp_path):
    """Zacian-Crowned is named at team preview by some teams and masked ('Zacian-*') then revealed for others:
    two populations (BR-06), never summed, and the two rows must not share a label."""
    zacian = [("all", "Zacian", 888, 10188, "zacian-crowned", "listed", 100, 50, 0),
              ("all", "Zacian", 888, 10188, "zacian-crowned", "observed", 150, 90, 0)]
    out = tmp_path / "web"
    manifest = export(_write(tmp_path, extra_rows=zacian), out)
    rows = _file(out, manifest, "all")[1]["rows"]
    zac = {r["label"]: (r["form_basis"], r["n"]) for r in rows if r["species"] == "Zacian"}
    assert zac == {"Zacian-Crowned": ("listed", 100), "Zacian-Crowned (seen in battle)": ("observed", 150)}


# --- partners and matchups (#13): species level, one file per regulation x band ----------------------------------

PARTNER_COLS = ["regulation", "rating_band", "species_a", "species_b", "species_a_id", "species_b_id", "teams_both",
                "teams_a", "teams_b", "teams_total", "wins_both", "share_of_a", "share_of_b", "lift", "win_rate",
                "win_ci_low", "win_ci_high", "band_win_rate", "win_rate_delta"]
MATCHUP_COLS = ["regulation", "rating_band", "species_a", "species_b", "species_a_id", "species_b_id", "battles", "wins",
                "teams_a", "win_rate", "win_ci_low", "win_ci_high", "a_win_rate", "win_rate_delta", "b_win_rate",
                "expected_win_rate", "win_rate_vs_expected", "z_vs_expected"]


def _write_pairs(agg, partner_rows=None, matchup_rows=None):
    """Synthetic pokemon_partner_stats / pokemon_matchup_stats as written by partner_stats / matchup_stats
    (species level, 'all' rows given, not a sum of bands). Derived columns are literal worked values."""
    partners = partner_rows if partner_rows is not None else [
        # band, a, b, a_id, b_id, teams_both, teams_a, teams_b, teams_total, wins_both, share_a, share_b, lift, wr, lo, hi, band_wr, delta
        ("all", "Incineroar", "Urshifu", 727, 892, 150, 300, 270, 1000, 90, 0.5, 0.55556, 1.85185, 0.6, 0.52, 0.68, 0.55, 0.05),
        ("all", "Calyrex", "Incineroar", 898, 727, 99, 299, 300, 1000, 60, 0.33, 0.33, 1.1, 0.61, 0.5, 0.7, 0.55, 0.06),
        ("all", "Calyrex", "Urshifu", 898, 892, 120, 299, 270, 1000, 50, 0.40134, 0.44444, 1.48637, 0.41667, 0.33, 0.5, 0.55, -0.13333),
        ("1500_plus", "Incineroar", "Urshifu", 727, 892, 100, 120, 100, 400, 45, 0.83333, 1.0, 3.33333, 0.45, 0.36, 0.55, 0.47, -0.02),
    ]
    matchups = matchup_rows if matchup_rows is not None else [
        # band, a, b, a_id, b_id, battles, wins, teams_a, wr, lo, hi, a_wr, delta, b_wr, expected, vs_expected, z
        ("all", "Incineroar", "Urshifu", 727, 892, 200, 90, 300, 0.45, 0.38, 0.52, 0.5, -0.05, 0.6, 0.4, 0.05, 1.44),
        ("all", "Urshifu", "Incineroar", 892, 727, 200, 110, 270, 0.55, 0.48, 0.62, 0.6, -0.05, 0.5, 0.6, -0.05, -1.44),
        ("all", "Incineroar", "Calyrex", 727, 898, 99, 40, 300, 0.40404, 0.31, 0.5, 0.5, -0.09596, 0.6, 0.4, 0.00404, 0.08),
        ("1500_plus", "Incineroar", "Urshifu", 727, 892, 100, 60, 120, 0.6, 0.5, 0.69, 0.6, 0.0, 0.6, 0.5, 0.1, 2.0),
    ]
    p = pd.DataFrame(partners, columns=PARTNER_COLS[1:]).assign(regulation=REG)[PARTNER_COLS]
    m = pd.DataFrame(matchups, columns=MATCHUP_COLS[1:]).assign(regulation=REG)[MATCHUP_COLS]
    p.to_parquet(agg / "pokemon_partner_stats.parquet", index=False)
    m.to_parquet(agg / "pokemon_matchup_stats.parquet", index=False)
    return agg


@pytest.fixture
def exported_pairs(tmp_path):
    out = tmp_path / "web"
    manifest = export(_write_pairs(_write(tmp_path)), out, batch_size=2)
    return out, manifest


def _pair_file(out, manifest, dataset, band):
    entry = next(f for f in manifest["datasets"][dataset] if f["rating_band"] == band)
    return json.loads((out / entry["path"]).read_text(encoding="utf-8"))


def _partners(out, manifest, band, species):
    rows = {r["species"]: r for r in _pair_file(out, manifest, "partners", band)["rows"]}
    return {p["species"]: p for p in rows[species]["partners"]} if species in rows else {}


def test_partner_pairs_below_100_teams_are_not_exported(exported_pairs):
    inc = _partners(*exported_pairs, "all", "Incineroar")
    assert set(inc) == {"Urshifu"}                                        # Calyrex: 99 teams < 100
    assert all(p["n"] >= 100 for p in inc.values())


def test_each_pair_is_listed_under_both_species_with_its_own_share(exported_pairs):
    inc, urs = _partners(*exported_pairs, "all", "Incineroar"), _partners(*exported_pairs, "all", "Urshifu")
    assert (inc["Urshifu"]["n"], inc["Urshifu"]["share"]) == (150, 0.5)          # P(Urshifu | Incineroar)
    assert (urs["Incineroar"]["n"], urs["Incineroar"]["share"]) == (150, 0.55556)   # P(Incineroar | Urshifu)
    assert inc["Urshifu"]["lift"] == urs["Incineroar"]["lift"] == 1.85185
    assert set(urs) == {"Incineroar", "Calyrex"}


def test_partner_bands_are_separate_files_and_all_is_taken_as_given(exported_pairs):
    out, manifest = exported_pairs
    assert [(f["rating_band"], f["path"]) for f in manifest["datasets"]["partners"]] == \
           [("all", f"partners/{REG}__all.json"), ("1500_plus", f"partners/{REG}__1500_plus.json")]
    assert _partners(out, manifest, "all", "Incineroar")["Urshifu"]["n"] == 150         # not 150 + 100
    top = _partners(out, manifest, "1500_plus", "Incineroar")["Urshifu"]
    assert (top["n"], top["share"], top["win_rate_delta"]) == (100, 0.83333, -0.02)


def _opponents(out, manifest, band, species):
    rows = {r["species"]: r for r in _pair_file(out, manifest, "matchups", band)["rows"]}
    return rows[species]["opponents"] if species in rows else []


def test_matchups_below_100_battles_are_dropped_and_carry_the_log5_expectation(exported_pairs):
    inc = _opponents(*exported_pairs, "all", "Incineroar")
    assert [o["species"] for o in inc] == ["Urshifu"]                     # vs Calyrex: 99 battles
    assert {k: inc[0][k] for k in ("n", "win_rate", "expected_win_rate", "win_rate_vs_expected", "z_vs_expected")} == \
           {"n": 200, "win_rate": 0.45, "expected_win_rate": 0.4, "win_rate_vs_expected": 0.05, "z_vs_expected": 1.44}
    assert _opponents(*exported_pairs, "1500_plus", "Incineroar")[0]["n"] == 100      # band kept separate


def test_matchups_keep_the_ends_of_the_expectation_gap_lowest_first(tmp_path, monkeypatch):
    monkeypatch.setattr("python.analytics.export_web.TOP_OPPONENTS", 2)
    rows = [("all", "Incineroar", f"S{z}", 727, 1000 + z, 300, 150, 300, 0.5, 0.44, 0.56, 0.5, 0.0, 0.5, 0.5, 0.0, float(z))
            for z in (0, -3, 2, 1, -1)]
    out = tmp_path / "web"
    manifest = export(_write_pairs(_write(tmp_path), matchup_rows=rows), out)
    assert [o["species"] for o in _opponents(out, manifest, "all", "Incineroar")] == ["S-3", "S-1", "S1", "S2"]


def test_partners_keep_the_most_frequent(tmp_path, monkeypatch):
    monkeypatch.setattr("python.analytics.export_web.TOP_PARTNERS", 2)
    rows = [("all", "Incineroar", f"P{n}", 727, n, n, 300, 300, 1000, n // 2, 0.5, 0.5, 1.0, 0.5, 0.4, 0.6, 0.5, 0.0)
            for n in (100, 300, 200)]
    out = tmp_path / "web"
    manifest = export(_write_pairs(_write(tmp_path), partner_rows=rows), out)
    assert list(_partners(out, manifest, "all", "Incineroar")) == ["P300", "P200"]


def test_partner_and_matchup_files_hold_only_allow_listed_keys(exported_pairs):
    out, manifest = exported_pairs
    for dataset, key, cols in (
            ("partners", "partners", ["species_id", "species", "n", "share", "lift", "win_rate", "win_ci_low",
                                      "win_ci_high", "win_rate_delta"]),
            ("matchups", "opponents", ["species_id", "species", "n", "win_rate", "win_ci_low", "win_ci_high",
                                       "win_rate_delta", "expected_win_rate", "win_rate_vs_expected", "z_vs_expected"])):
        for f in manifest["datasets"][dataset]:
            data = json.loads((out / f["path"]).read_text(encoding="utf-8"))
            assert list(data) == ["regulation", "rating_band", "min_n", "rows"]
            assert f["rows"] == len(data["rows"]) and f["bytes"] == (out / f["path"]).stat().st_size
            for r in data["rows"]:
                assert list(r) == ["species_id", "species", key]
                assert all(list(i) == cols for i in r[key])


@pytest.mark.parametrize("table", ["pokemon_partner_stats", "pokemon_matchup_stats"])
def test_a_forbidden_column_in_a_pair_table_makes_the_export_fail_without_writing(tmp_path, table):
    agg, out = _write_pairs(_write(tmp_path)), tmp_path / "web"
    df = pd.read_parquet(agg / f"{table}.parquet").assign(username="x")
    df.to_parquet(agg / f"{table}.parquet", index=False)
    with pytest.raises(ExportError, match="username"):
        export(agg, out)
    assert not out.exists()


def test_missing_pair_tables_give_empty_datasets_and_remove_stale_files(tmp_path):
    out = tmp_path / "web"
    stale = out / "partners" / f"{REG}__all.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}", encoding="utf-8")
    manifest = export(_write(tmp_path), out)
    assert (manifest["datasets"]["partners"], manifest["datasets"]["matchups"]) == ([], [])
    assert not stale.exists()


def test_csv_pair_tables_give_the_same_export(tmp_path):
    agg = _write_pairs(_write(tmp_path))
    a = export(agg, tmp_path / "a", snapshot_date="2026-01-01")
    for t in ("pokemon_partner_stats", "pokemon_matchup_stats"):
        pd.read_parquet(agg / f"{t}.parquet").to_csv(agg / f"{t}.csv", index=False)
        (agg / f"{t}.parquet").unlink()
    b = export(agg, tmp_path / "b", snapshot_date="2026-01-01", batch_size=1)
    assert a == b
    for f in a["datasets"]["partners"] + a["datasets"]["matchups"]:
        assert (tmp_path / "a" / f["path"]).read_text() == (tmp_path / "b" / f["path"]).read_text()


MONTHLY_COLS = ["regulation", "month", "rating_band", "species", "species_id", "appearances", "wins", "sent_out",
                "player_battles", "tail", "usage_share", "win_rate", "win_ci_low", "win_ci_high", "sent_out_rate"]


def _write_monthly(agg, rows=None):
    """Synthetic pokemon_usage_monthly as written by usage_trend (species level, 'all' rows given, tail per month)."""
    rows = rows if rows is not None else [
        # month, band, species, species_id, appearances, wins, player_battles, tail, ci_low, ci_high
        ("2024-01", "all", "Incineroar", 727, 400, 200, 1000, False, 0.45, 0.55),
        ("2024-01", "all", "Urshifu", 892, 99, 50, 1000, False, 0.4, 0.6),         # n < 100: point dropped
        ("2024-02", "all", "Incineroar", 727, 300, 180, 800, False, 0.54, 0.65),
        ("2024-02", "all", "Urshifu", 892, 200, 90, 800, False, 0.38, 0.52),
        ("2024-03", "all", "Incineroar", 727, 100, 40, 40, True, 0.31, 0.5),          # tail month: kept and flagged
        ("unknown", "all", "Incineroar", 727, 150, 75, 200, False, 0.42, 0.58),       # no upload time: not a month
        ("2024-01", "1500_plus", "Incineroar", 727, 120, 72, 300, False, 0.51, 0.68),
        ("2024-01", "1500_plus", "Urshifu", 892, 50, 20, 300, False, 0.28, 0.54),
    ]
    df = pd.DataFrame(rows, columns=["month", "rating_band", "species", "species_id", "appearances", "wins",
                                     "player_battles", "tail", "win_ci_low", "win_ci_high"]).assign(regulation=REG)
    df["sent_out"] = df["appearances"]
    df["usage_share"] = df["appearances"] / df["player_battles"]
    df["win_rate"] = df["wins"] / df["appearances"]
    df["sent_out_rate"] = 1.0
    df[MONTHLY_COLS].to_parquet(agg / "pokemon_usage_monthly.parquet", index=False)
    return agg


@pytest.fixture
def exported_trend(tmp_path):
    out = tmp_path / "web"
    manifest = export(_write_monthly(_write(tmp_path)), out, batch_size=2)
    return out, manifest


def _trend_file(out, manifest, band):
    entry = next(f for f in manifest["datasets"]["trend"] if f["rating_band"] == band)
    return json.loads((out / entry["path"]).read_text(encoding="utf-8"))


def _points(data, species):
    rows = {r["species"]: r for r in data["rows"]}
    return {p["month"]: p for p in rows[species]["points"]} if species in rows else {}


def test_trend_months_are_listed_with_their_tail_flag_and_unknown_month_dropped(exported_trend):
    data = _trend_file(*exported_trend, "all")
    assert data["months"] == [{"month": "2024-01", "player_battles": 1000, "tail": False},
                              {"month": "2024-02", "player_battles": 800, "tail": False},
                              {"month": "2024-03", "player_battles": 40, "tail": True}]
    assert set(_points(data, "Incineroar")) == {"2024-01", "2024-02", "2024-03"}      # tail point kept in the export


def test_trend_points_below_100_teams_are_dropped(exported_trend):
    data = _trend_file(*exported_trend, "all")
    assert set(_points(data, "Urshifu")) == {"2024-02"}                                # 2024-01: 99 teams
    p = _points(data, "Urshifu")["2024-02"]
    assert (p["n"], p["usage_share"], p["win_rate"], p["win_ci_low"], p["win_ci_high"]) == (200, 0.25, 0.45, 0.38, 0.52)


def test_trend_bands_are_separate_files_and_all_is_taken_as_given(exported_trend):
    out, manifest = exported_trend
    assert [(f["rating_band"], f["path"]) for f in manifest["datasets"]["trend"]] == \
           [("all", f"trend/{REG}__all.json"), ("1500_plus", f"trend/{REG}__1500_plus.json")]
    top = _trend_file(out, manifest, "1500_plus")
    assert top["months"] == [{"month": "2024-01", "player_battles": 300, "tail": False}]
    assert _points(top, "Incineroar")["2024-01"]["n"] == 120 and _points(top, "Urshifu") == {}
    assert _points(_trend_file(out, manifest, "all"), "Incineroar")["2024-01"]["n"] == 400    # not 400 + 120


def test_trend_files_hold_only_allow_listed_keys(exported_trend):
    out, manifest = exported_trend
    for f in manifest["datasets"]["trend"]:
        data = json.loads((out / f["path"]).read_text(encoding="utf-8"))
        assert list(data) == ["regulation", "rating_band", "min_n", "months", "rows"]
        assert f["rows"] == len(data["rows"]) and f["bytes"] == (out / f["path"]).stat().st_size
        for r in data["rows"]:
            assert list(r) == ["species_id", "species", "points"]
            assert all(list(p) == ["month", "n", "usage_share", "win_rate", "win_ci_low", "win_ci_high"] for p in r["points"])


def test_a_monthly_table_without_rating_band_is_refused(tmp_path):
    agg = _write_monthly(_write(tmp_path))
    df = pd.read_parquet(agg / "pokemon_usage_monthly.parquet")
    df[df["rating_band"] == "all"].drop(columns="rating_band").to_parquet(agg / "pokemon_usage_monthly.parquet", index=False)
    with pytest.raises(ExportError, match="usage_trend"):
        export(agg, tmp_path / "web")


def test_a_missing_monthly_table_gives_an_empty_trend_dataset(tmp_path):
    assert export(_write(tmp_path), tmp_path / "web")["datasets"]["trend"] == []


TERA_SUMMARY_COLS = ["regulation", "rating_band", "species", "species_id", "sent_out", "sent_out_wins", "tera_events",
                     "tera_wins", "tera_rate", "tera_rate_ci_low", "tera_rate_ci_high", "win_rate_tera", "win_rate_no_tera"]
TERA_TYPE_COLS = ["regulation", "species_id", "species", "tera_type", "events", "wins", "rating_band", "tera_events",
                  "tera_wins", "type_share"]


def _write_tera(agg, summary_rows=None):
    """Synthetic pokemon_tera_summary / pokemon_tera_types as written by tera_stats ('all' rows given)."""
    summary = summary_rows if summary_rows is not None else [
        # band, species, id, sent_out, sent_out_wins, tera_events, tera_wins, rate, lo, hi, win_tera, win_no_tera
        ("all", "Incineroar", 727, 400, 200, 150, 90, 0.375, 0.33, 0.42, 0.6, 0.44),
        ("all", "Urshifu", 892, 250, 120, 60, 30, 0.24, 0.19, 0.3, 0.5, 0.47368),          # 60 Tera: win rate hidden
        ("all", "Rare", 1, 99, 50, 99, 50, 1.0, 0.96, 1.0, 0.50505, None),                 # sent out 99 < 100
        ("all", "Calyrex", 898, 150, 80, 0, 0, 0.0, 0.0, 0.02, None, 0.53333),             # never Terastallized
        ("1500_plus", "Incineroar", 727, 120, 60, 100, 55, 0.83333, 0.75, 0.89, 0.55, 0.25),
    ]
    s = pd.DataFrame(summary, columns=["rating_band", "species", "species_id", "sent_out", "sent_out_wins", "tera_events",
                                       "tera_wins", "tera_rate", "tera_rate_ci_low", "tera_rate_ci_high",
                                       "win_rate_tera", "win_rate_no_tera"]).assign(regulation=REG)
    types = [  # band, species, id, type, events, tera_events, share
        ("all", "Incineroar", 727, "Ghost", 120, 150, 0.8), ("all", "Incineroar", 727, "Grass", 30, 150, 0.2),
        ("all", "Urshifu", 892, "Water", 60, 60, 1.0),
        ("1500_plus", "Incineroar", 727, "Ghost", 100, 100, 1.0),
    ]
    t = pd.DataFrame(types, columns=["rating_band", "species", "species_id", "tera_type", "events", "tera_events",
                                     "type_share"]).assign(regulation=REG, wins=1, tera_wins=1)
    s[TERA_SUMMARY_COLS].to_parquet(agg / "pokemon_tera_summary.parquet", index=False)
    t[TERA_TYPE_COLS].to_parquet(agg / "pokemon_tera_types.parquet", index=False)
    return agg


@pytest.fixture
def exported_tera(tmp_path):
    out = tmp_path / "web"
    manifest = export(_write_tera(_write(tmp_path)), out, batch_size=2)
    return out, manifest


def _tera(out, manifest, band):
    entry = next(f for f in manifest["datasets"]["tera"] if f["rating_band"] == band)
    return {r["species"]: r for r in json.loads((out / entry["path"]).read_text(encoding="utf-8"))["rows"]}


def test_tera_rows_below_100_sent_out_are_dropped(exported_tera):
    assert set(_tera(*exported_tera, "all")) == {"Incineroar", "Urshifu", "Calyrex"}     # Rare: 99 sent out


def test_tera_rate_and_types_of_a_species(exported_tera):
    inc = _tera(*exported_tera, "all")["Incineroar"]
    assert {k: inc[k] for k in ("n", "tera_events", "tera_rate", "tera_rate_ci_low", "tera_rate_ci_high")} == \
           {"n": 400, "tera_events": 150, "tera_rate": 0.375, "tera_rate_ci_low": 0.33, "tera_rate_ci_high": 0.42}
    assert inc["types"] == [{"tera_type": "Ghost", "events": 120, "type_share": 0.8},
                            {"tera_type": "Grass", "events": 30, "type_share": 0.2}]       # most used first


def test_tera_win_rates_and_types_with_fewer_than_100_games_are_hidden(exported_tera):
    rows = _tera(*exported_tera, "all")
    urs, cal = rows["Urshifu"], rows["Calyrex"]
    assert (urs["win_rate_tera"], urs["win_rate_no_tera"], urs["types"]) == (None, 0.47368, [])   # 60 Tera games
    assert (cal["tera_events"], cal["win_rate_tera"], cal["win_rate_no_tera"]) == (0, None, 0.53333)
    inc = _tera(*exported_tera, "1500_plus")["Incineroar"]
    assert (inc["win_rate_tera"], inc["win_rate_no_tera"]) == (0.55, None)                 # 20 games without Tera


def test_tera_bands_are_separate_files(exported_tera):
    out, manifest = exported_tera
    assert [(f["rating_band"], f["path"]) for f in manifest["datasets"]["tera"]] == \
           [("all", f"tera/{REG}__all.json"), ("1500_plus", f"tera/{REG}__1500_plus.json")]
    assert _tera(out, manifest, "1500_plus")["Incineroar"]["types"] == [{"tera_type": "Ghost", "events": 100, "type_share": 1.0}]


def test_tera_files_hold_only_allow_listed_keys(exported_tera):
    out, manifest = exported_tera
    for f in manifest["datasets"]["tera"]:
        data = json.loads((out / f["path"]).read_text(encoding="utf-8"))
        assert list(data) == ["regulation", "rating_band", "min_n", "rows"]
        assert f["rows"] == len(data["rows"]) and f["bytes"] == (out / f["path"]).stat().st_size
        for r in data["rows"]:
            assert list(r) == ["species_id", "species", "n", "tera_events", "tera_rate", "tera_rate_ci_low",
                               "tera_rate_ci_high", "win_rate_tera", "win_rate_no_tera", "types"]
            assert all(list(t) == ["tera_type", "events", "type_share"] for t in r["types"])


@pytest.mark.parametrize("table", ["pokemon_tera_summary", "pokemon_tera_types"])
def test_a_forbidden_column_in_a_tera_table_makes_the_export_fail_without_writing(tmp_path, table):
    agg, out = _write_tera(_write(tmp_path)), tmp_path / "web"
    pd.read_parquet(agg / f"{table}.parquet").assign(battle_id="b1").to_parquet(agg / f"{table}.parquet", index=False)
    with pytest.raises(ExportError, match="battle_id"):
        export(agg, out)
    assert not out.exists()


def test_missing_tera_and_trend_tables_remove_stale_files(tmp_path):
    out = tmp_path / "web"
    for d in ("tera", "trend"):
        (out / d).mkdir(parents=True)
        (out / d / f"{REG}__all.json").write_text("{}", encoding="utf-8")
    manifest = export(_write(tmp_path), out)
    assert manifest["datasets"]["tera"] == [] and manifest["schema_version"] == 4
    assert not any((out / d / f"{REG}__all.json").exists() for d in ("tera", "trend"))
