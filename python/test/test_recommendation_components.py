"""Usage component of the v2.0 recommender (#50), on the synthetic Parquet of the pokemon-usage tests."""
import pandas as pd
import pytest

from python.recommendation.components import main, usage_component
from python.test.test_pokemon_usage import REG, _write


def _row(comp, species_id, poke_id, basis, band="all"):
    sel = comp[(comp["species_id"] == species_id) & (comp["form_basis"] == basis) & (comp["rating_band"] == band)]
    sel = sel[sel["poke_id"].isna()] if poke_id is None else sel[sel["poke_id"] == poke_id]
    assert len(sel) == 1
    return sel.iloc[0]


def test_usage_and_n_per_regulation_and_band_match_hand_counts(tmp_path):
    out, name_map = _write(tmp_path)
    comp = usage_component(out, name_map, batch_size=3)
    inc = _row(comp, 727, 727, "listed")                                  # b1 p1 only; b3-b5 out of scope
    assert (inc["regulation"], inc["appearances"], inc["player_battles"], inc["usage_share"]) == (REG, 1, 4, 0.25)
    rapid = _row(comp, 892, 10191, "observed", "1200_1399")               # b1 p1, rating 1250
    assert (rapid["appearances"], rapid["player_battles"], rapid["usage_share"]) == (1, 1, 1.0)
    assert (rapid["species"], rapid["form"]) == ("Urshifu", "urshifu-rapid-strike")


def test_restricting_to_a_battle_subset_counts_only_those_battles(tmp_path):
    out, name_map = _write(tmp_path)
    comp = usage_component(out, name_map, battle_ids=["b2", "b3", "zz"], batch_size=3)   # b3 out of scope, zz unknown
    alls = comp[comp["rating_band"] == "all"]
    assert set(alls["player_battles"]) == {2} and alls["appearances"].sum() == 2         # b2: Urshifu (p2) + Arceus-Fire (p1)
    assert 727 not in set(comp["species_id"])                                            # Incineroar is only in b1
    single = _row(comp, 892, 892, "observed")
    assert (single["appearances"], single["usage_share"]) == (1, 0.5)


def test_a_subset_with_no_battle_in_the_population_fails_loudly(tmp_path):
    out, name_map = _write(tmp_path)
    with pytest.raises(ValueError, match="none of the 2 battle_ids"):
        usage_component(out, name_map, battle_ids=["b3", "zz"])                       # b3: other format


def test_all_is_its_own_band_and_each_band_has_its_own_n(tmp_path):
    out, name_map = _write(tmp_path)
    comp = usage_component(out, name_map, batch_size=3)
    n = comp.groupby("rating_band")["player_battles"].unique().map(list).to_dict()
    assert n == {"all": [4], "below_1200": [1], "1200_1399": [1], "1500_plus": [1], "unknown": [1]}
    assert comp.duplicated(["regulation", "rating_band", "species_id", "poke_id", "form_basis"]).sum() == 0
    assert comp[comp["rating_band"] == "all"]["appearances"].sum() == 5               # 'all' counted once, not band rows + 'all'


def test_cli_prints_rows_per_regulation_and_band(tmp_path, capsys):
    out, name_map = _write(tmp_path)
    name_map.to_csv(tmp_path / "map.csv", index=False)
    assert main(["--output-dir", str(out), "--map", str(tmp_path / "map.csv"), "--out", str(tmp_path / "agg")]) == 0
    printed = capsys.readouterr().out
    assert len(pd.read_parquet(tmp_path / "agg" / "recommendation_usage_component.parquet")) == 10   # 5 'all' rows + 5 band rows
    assert "one n per regulation/band: True" in printed and "band n add up to 'all' n: True" in printed
    assert "band appearances add up to 'all': True" in printed
