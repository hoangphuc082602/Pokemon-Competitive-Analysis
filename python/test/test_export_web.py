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
    assert manifest["schema_version"] == 2 and manifest["min_n"] == 100
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
