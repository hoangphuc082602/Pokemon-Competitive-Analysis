"""Seam 1: aggregate directory in -> static web data out (python.analytics.export_web)."""
import json

import pandas as pd
import pytest

from python.analytics.export_web import ExportError, export

REG = "gen9vgc2024regg"


def _write(tmp_path, extra_cols=None):
    """Synthetic aggregates as written by pokemon_usage (form grain, 'all' band rows included).
    The export reads aggregates, not event tables, so this mirrors test_pokemon_usage._write at the next layer:
    counts chosen so that 'all' differs from the sum of bands and n crosses the threshold."""
    agg = tmp_path / "agg"
    agg.mkdir()
    rows = [  # band, species, species_id, poke_id, form_basis, appearances, wins, leads
        ("all", "Urshifu", 892, 10191, "observed", 150, 90, 60),
        ("all", "Urshifu", 892, None, "unobserved", 50, 20, 0),   # same species: 200 together
        ("all", "Incineroar", 727, 727, "listed", 300, 150, 150),
        ("all", "Rare", 1, 1, "listed", 99, 99, 0),               # n < 100: hidden, but still in the baseline
        ("1500_plus", "Incineroar", 727, 727, "listed", 120, 72, 60),
        ("1500_plus", "Urshifu", 892, 10191, "observed", 100, 40, 10),
        ("1500_plus", "Rare", 1, 1, "listed", 20, 0, 0),
        # 'all' deliberately differs from the sum of bands: the export must take 'all' rows as given
    ]
    df = pd.DataFrame(rows, columns=["rating_band", "species", "species_id", "poke_id", "form_basis",
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
    return {r["species"]: r for r in _file(out, manifest, band)[1]["rows"]}


def test_species_below_100_player_battles_are_not_exported(exported):
    rows = _rows(*exported, "all")
    assert set(rows) == {"Urshifu", "Incineroar"}
    assert all(r["n"] >= 100 for r in rows.values())


def test_forms_are_summed_to_the_species_total(exported):
    urshifu = _rows(*exported, "all")["Urshifu"]
    assert (urshifu["n"], urshifu["win_rate"]) == (200, 0.55)              # 150 observed + 50 unobserved


def test_win_rate_delta_is_against_the_bands_own_baseline(exported):
    out, manifest = exported
    _, top = _file(out, manifest, "1500_plus")
    assert top["baseline_win_rate"] == pytest.approx(112 / 240, abs=1e-5)  # all species of the band, Rare included
    inc = _rows(out, manifest, "1500_plus")["Incineroar"]
    assert inc["win_rate_delta"] == pytest.approx(0.6 - 112 / 240, abs=1e-5)
    assert _rows(out, manifest, "all")["Incineroar"]["win_rate_delta"] == pytest.approx(0.5 - 359 / 599, abs=1e-5)


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
            assert list(r) == ["species_id", "species", "n", "usage_share", "win_rate", "win_ci_low", "win_ci_high",
                               "win_rate_delta", "lead_rate"]


def test_manifest_counts_and_sizes_match_the_files(exported):
    out, manifest = exported
    assert manifest["schema_version"] == 1 and manifest["min_n"] == 100
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
