import pandas as pd
import pytest

from python.models.team_builder import build_pokemon

IVS = dict.fromkeys(["hp", "atk", "def", "spatk", "spdef", "spe"], 31)


@pytest.fixture
def stats_df():
    # Cột giống kết quả của load_all_pokemon_stats()
    return pd.DataFrame(
        [
            ("garchomp", "dragon", "ground", 108, 130, 95, 80, 85, 102),
            ("ditto", "normal", None, 48, 48, 48, 48, 48, 48),
        ],
        columns=["pokemon", "type_1", "type_2", "hp", "atk", "def", "spatk", "spdef", "spe"],
    )


def build(stats_df, nature_df, name="garchomp", **overrides):
    kwargs = dict(
        level=50, nature="jolly", ability="rough-skin", item="choice-scarf",
        moves=["earthquake", "dragon-claw"], ivs=IVS,
        evs={"hp": 0, "atk": 252, "def": 0, "spatk": 0, "spdef": 4, "spe": 252},
    )
    kwargs.update(overrides)
    return build_pokemon(stats_df, nature_df, pokemon_name=name, **kwargs)


def test_build_garchomp_final_stats(stats_df):
    nature_df = pd.DataFrame([("jolly", 6, 4)], columns=["nature_name", "increased_stat", "decreased_stat"])
    mon = build(stats_df, nature_df)

    assert mon["stats"] == {"hp": 183, "atk": 182, "def": 115, "spatk": 90, "spdef": 106, "spe": 169}


def test_build_keeps_input_fields(stats_df, nature_df):
    mon = build(stats_df, nature_df, nature="adamant")
    assert mon["name"] == "garchomp"
    assert mon["types"] == ["dragon", "ground"]
    assert (mon["level"], mon["nature"], mon["ability"], mon["item"]) == (50, "adamant", "rough-skin", "choice-scarf")
    assert mon["moves"] == ["earthquake", "dragon-claw"]


def test_single_type_pokemon_has_missing_second_type(stats_df, nature_df):
    mon = build(stats_df, nature_df, name="ditto", nature="hardy")
    assert mon["types"][0] == "normal"
    assert pd.isna(mon["types"][1])


def test_unknown_pokemon_raises(stats_df, nature_df):
    # Hành vi hiện tại: IndexError (iloc[0] trên kết quả rỗng). Test cũ gõ nhầm "rottom" và không hề assert.
    with pytest.raises(IndexError):
        build(stats_df, nature_df, name="rottom")