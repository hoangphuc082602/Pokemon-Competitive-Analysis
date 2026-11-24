"""Speed calculation (#19): level-50 Speed stat plus the held items that change it (Choice Scarf, Iron Ball)."""
import pytest

from python.calculations.speed_calc import calculate_speed


@pytest.mark.parametrize("base,iv,ev,nature,expected", [
    (100, 31, 252, 1.1, 167),   # max Speed, +Spe nature
    (100, 31, 252, 1.0, 152),
    (100, 31, 0, 1.0, 120),
    (100, 0, 0, 0.9, 94),       # floor(105 * 0.9): Trick Room spread
    (30, 31, 0, 1.0, 50),     # floor(91 * 50 / 100) + 5
])
def test_level_50_speed_known_values(base, iv, ev, nature, expected):
    assert calculate_speed(base, iv, ev, 50, nature) == expected


@pytest.mark.parametrize("item", ["choice-scarf", "Choice Scarf"])   # PokéAPI slug or display name
def test_choice_scarf_multiplies_by_1_5_rounded_down(item):
    assert calculate_speed(100, 31, 252, 50, 1.1, item) == 250        # floor(167 * 1.5)
    assert calculate_speed(100, 31, 0, 50, 1.0, item) == 180


@pytest.mark.parametrize("item", ["iron-ball", "Iron Ball"])
def test_iron_ball_halves_rounded_down(item):
    assert calculate_speed(100, 31, 252, 50, 1.1, item) == 83          # floor(167 * 0.5)


@pytest.mark.parametrize("item", [None, "", "life-orb", "silk-scarf"])
def test_other_items_leave_speed_unchanged(item):
    assert calculate_speed(100, 31, 252, 50, 1.1, item) == 167
