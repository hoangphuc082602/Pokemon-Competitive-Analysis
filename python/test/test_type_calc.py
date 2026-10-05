import pytest

from python.calculations.type_calc import calculate_type_multiplier, get_actual_move_type


def calc(chart, attacker, defender, move_type):
    return calculate_type_multiplier(chart, attacker, defender, {"type": move_type})


# ---------- type chart cơ bản ----------
def test_super_effective(type_chart_df, battler):
    assert calc(type_chart_df, battler(["fire"]), battler(["grass"]), "fire") == 2.0


def test_not_very_effective_double_resist(type_chart_df, battler):
    # fire vs water/fire = 0.5 * 0.5
    assert calc(type_chart_df, battler(["fire"]), battler(["water", "fire"]), "fire") == 0.25


def test_dual_type_neutralised(type_chart_df, battler):
    # electric vs water/ground: 2.0 * 0.0
    assert calc(type_chart_df, battler(["electric"]), battler(["water", "ground"]), "electric") == 0.0


def test_missing_pair_defaults_to_neutral(type_chart_df, battler):
    assert calc(type_chart_df, battler(["water"]), battler(["grass"]), "water") == 1.0


def test_none_second_type_is_ignored(type_chart_df, battler):
    assert calc(type_chart_df, battler(["fire"]), battler(["grass", None]), "fire") == 2.0


def test_type_names_are_case_insensitive(type_chart_df, battler):
    assert calc(type_chart_df, battler(["fire"], ability="Blaze"), battler(["Grass"]), "Fire") == 2.0


# ---------- ability phòng thủ ----------
@pytest.mark.parametrize(
    "ability, move_type, defender_types",
    [
        ("levitate", "ground", ["electric"]),       # ground vs electric vốn là 2x
        ("flash-fire", "fire", ["grass"]),
        ("water-absorb", "water", ["fire"]),
        ("lightning-rod", "electric", ["water"]),
        ("earth-eater", "ground", ["fire"]),
    ],
)
def test_ability_immunity(type_chart_df, battler, ability, move_type, defender_types):
    assert calc(type_chart_df, battler(["normal"]), battler(defender_types, ability=ability), move_type) == 0.0


def test_thick_fat_halves_fire(type_chart_df, battler):
    # fire vs grass 2x, thick-fat 0.5x
    assert calc(type_chart_df, battler(["fire"]), battler(["grass"], ability="thick-fat"), "fire") == 1.0


def test_thick_fat_does_not_affect_other_types(type_chart_df, battler):
    # water vs grass không có trong chart -> 1x; Thick Fat chỉ giảm fire/ice
    defender = battler(["grass"], ability="thick-fat")
    assert calc(type_chart_df, battler(["water"]), defender, "water") == 1.0


def test_mold_breaker_ignores_immunity(type_chart_df, battler):
    attacker = battler(["ground"], ability="mold-breaker")
    defender = battler(["electric"], ability="levitate")
    assert calc(type_chart_df, attacker, defender, "ground") == 2.0


def test_mold_breaker_ignores_thick_fat(type_chart_df, battler):
    attacker = battler(["fire"], ability="mold-breaker")
    defender = battler(["grass"], ability="thick-fat")
    assert calc(type_chart_df, attacker, defender, "fire") == 2.0


# ---------- ability tấn công ----------
@pytest.mark.parametrize("move_type", ["normal", "fighting"])
def test_scrappy_hits_ghost(type_chart_df, battler, move_type):
    assert calc(type_chart_df, battler(["normal"], ability="scrappy"), battler(["ghost"]), move_type) == 1.0


def test_normal_move_cannot_hit_ghost_without_scrappy(type_chart_df, battler):
    assert calc(type_chart_df, battler(["normal"]), battler(["ghost"]), "normal") == 0.0


def test_pixilate_turns_normal_move_into_fairy(type_chart_df, battler):
    attacker = battler(["normal"], ability="pixilate")
    assert get_actual_move_type(attacker, {"type": "normal"}) == "fairy"
    # fairy vs dragon = 2x
    assert calc(type_chart_df, attacker, battler(["dragon"]), "normal") == 2.0


def test_pixilate_does_not_change_non_normal_move(type_chart_df, battler):
    attacker = battler(["normal"], ability="pixilate")
    assert get_actual_move_type(attacker, {"type": "fire"}) == "fire"


# ---------- Cơ chế đã sửa (trước đây là xfail) ----------
def test_normalize_converts_any_move_to_normal(battler):
    assert get_actual_move_type(battler(["normal"], ability="normalize"), {"type": "fire"}) == "normal"


def test_wind_rider_does_not_block_all_flying_moves(type_chart_df, battler):
    # Wind Rider chỉ miễn nhiễm move "gió" (Tailwind, Hurricane...), không miễn nhiễm cả hệ Flying.
    defender = battler(["grass"], ability="wind-rider")
    assert calc(type_chart_df, battler(["flying"]), defender, "flying") == 2.0


@pytest.mark.parametrize("name", ["flash-fire", "Flash Fire", "flash fire", "FLASH_FIRE", " flash-fire "])
def test_ability_name_formats_are_normalised(type_chart_df, battler, name):
    defender = battler(["grass"], ability=name)
    assert calc(type_chart_df, battler(["fire"]), defender, "fire") == 0.0