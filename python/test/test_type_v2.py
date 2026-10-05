import pytest

from python.calculations.type_v2 import (
    analyze_team_defense,
    calculate_defensive_multiplier,
    get_pokemon_types,
)


def mon(name, ability="none"):
    return {"pokemon": name, "ability": ability}


# ---------- get_pokemon_types ----------
def test_types_dual(pokemon_df):
    assert get_pokemon_types(pokemon_df, "incineroar") == ["fire", "dark"]


def test_types_single_drops_missing_second_type(pokemon_df):
    assert get_pokemon_types(pokemon_df, "ditto") == ["normal"]


def test_types_unknown_pokemon_returns_empty_list(pokemon_df):
    # Hành vi hiện tại: tên không có trong bảng -> [] (sau đó mọi đòn đều bị tính 1x).
    assert get_pokemon_types(pokemon_df, "missingno") == []


# ---------- calculate_defensive_multiplier ----------
def test_double_weakness_is_4x(type_chart_df, pokemon_df):
    # electric vs water/flying = 2 * 2
    assert calculate_defensive_multiplier(type_chart_df, pokemon_df, "electric", mon("pelipper")) == 4


def test_type_immunity_from_second_type(type_chart_df, pokemon_df):
    # ground vs water/flying = 1 * 0
    assert calculate_defensive_multiplier(type_chart_df, pokemon_df, "ground", mon("pelipper")) == 0


def test_ability_immunity_and_ignore_flag(type_chart_df, pokemon_df):
    defender = mon("rotom-wash", "levitate")  # electric/water: ground vốn là 2x
    assert calculate_defensive_multiplier(type_chart_df, pokemon_df, "ground", defender) == 0.0
    assert calculate_defensive_multiplier(
        type_chart_df, pokemon_df, "ground", defender, ignore_defender_ability=True
    ) == 2.0


def test_ability_resistance_stacks_with_types(type_chart_df, pokemon_df):
    # fire vs fire/dark = 0.5, thick-fat thêm 0.5
    assert calculate_defensive_multiplier(
        type_chart_df, pokemon_df, "fire", mon("incineroar", "thick-fat")
    ) == 0.25


def test_attack_type_is_case_insensitive(type_chart_df, pokemon_df):
    assert calculate_defensive_multiplier(type_chart_df, pokemon_df, "ELECTRIC", mon("pelipper")) == 4


# ---------- analyze_team_defense ----------
@pytest.fixture
def team_report(type_chart_df, pokemon_df):
    team = [mon("pelipper", "drizzle"), mon("rotom-wash", "levitate")]
    return analyze_team_defense(type_chart_df, pokemon_df, team)


def test_team_defense_buckets_and_net(team_report):
    electric = team_report["by_type"]["electric"]
    assert (electric["4x"], electric["2x"]) == (1, 1)   # pelipper 4x, rotom-wash 2x
    assert electric["net"] == 3                          # 1*2 + 1

    ground = team_report["by_type"]["ground"]
    assert ground["0x"] == 2                             # pelipper (flying) + rotom (levitate)
    assert ground["net"] == -4                           # -(2 * 2)

    fire = team_report["by_type"]["fire"]
    assert fire["0.5x"] == 2 and fire["net"] == -2


def test_team_defense_summary(team_report):
    summary = team_report["summary"]
    assert summary["4x_weaknesses"] == ["electric"]
    assert "ground" in summary["well_covered"]
    assert "electric" not in summary["well_covered"]


def test_team_defense_rejects_non_list(type_chart_df, pokemon_df):
    with pytest.raises(AssertionError):
        analyze_team_defense(type_chart_df, pokemon_df, mon("pelipper"))


@pytest.mark.parametrize("ability", ["levitate", "Levitate", "LEVITATE"])
def test_defender_ability_name_formats(type_chart_df, pokemon_df, ability):
    assert calculate_defensive_multiplier(
        type_chart_df, pokemon_df, "ground", mon("rotom-wash", ability)
    ) == 0.0


def test_defender_ability_with_space_in_display_name(type_chart_df, pokemon_df):
    # "Thick Fat" (tên hiển thị) phải khớp slug "thick-fat": fire vs fire/dark = 0.5, thêm 0.5
    assert calculate_defensive_multiplier(
        type_chart_df, pokemon_df, "fire", mon("incineroar", "Thick Fat")
    ) == 0.25