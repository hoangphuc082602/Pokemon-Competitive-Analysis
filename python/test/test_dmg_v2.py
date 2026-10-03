import random

import pytest

from python.calculations.base_damage import calc_base_damage
from python.calculations.damage_calc_v2 import calculate_damage
from python.calculations.get_battle_stats import get_battle_stats
from python.calculations.percentage_ko import calculate_2hko_chance, calculate_ohko_chance
from python.calculations.stab_modifier import get_stab_modifier


def move(type_, power=80, damage_class="physical"):
    return {"type": type_, "power": power, "damage_class": damage_class}


@pytest.fixture
def fixed_roll(monkeypatch):
    """calculate_damage dùng random.uniform -> cố định roll để test lặp lại được."""

    def _set(value):
        monkeypatch.setattr(random, "uniform", lambda a, b: value)

    return _set


# ---------- thành phần ----------
def test_base_damage_formula():
    # ((2*50/5 + 2) * 80 * 100 / 100) / 50 + 2 = (22 * 80) / 50 + 2 = 37.2
    assert calc_base_damage({"level": 50}, {"power": 80}, 100, 100) == pytest.approx(37.2)


def test_stab(battler):
    assert get_stab_modifier(battler(["fire", "dark"]), {"type": "fire"}) == 1.5
    assert get_stab_modifier(battler(["fire", "dark"]), {"type": "water"}) == 1


def test_battle_stats_pick_physical_or_special(battler):
    attacker = battler(["fire"], atk=130, spatk=60)
    defender = battler(["grass"], **{"def": 90, "spdef": 70})
    assert get_battle_stats(attacker, defender, move("fire", damage_class="physical")) == (130, 90)
    assert get_battle_stats(attacker, defender, move("fire", damage_class="special")) == (60, 70)


# ---------- KO probability ----------
def test_ohko_all_rolls_kill_when_hp_at_or_below_lowest_roll():
    # roll thấp nhất = int(111 * 0.85) = 94
    assert calculate_ohko_chance(94, 111, 94) == 100.0


def test_ohko_none_kill_when_hp_above_max():
    assert calculate_ohko_chance(94, 111, 112) == 0.0


def test_ohko_partial():
    # int(111 * i/100) >= 100 khi i >= 91 -> 10 trong 16 roll
    assert calculate_ohko_chance(94, 111, 100) == 62.5


def test_2hko_partial():
    # Cần dmg >= 100 (HP 200 / 2) -> 10 trong 16 roll
    assert calculate_2hko_chance(94, 111, 200) == 62.5


# ---------- calculate_damage ----------
def test_stab_super_effective_known_values(type_chart_df, battler, fixed_roll):
    attacker = battler(["fire"])
    defender = battler(["grass"], hp=100)
    # base 37.2 * STAB 1.5 * type 2.0 = 111.6
    fixed_roll(1.0)
    result = calculate_damage(attacker, defender, move("fire"), type_chart_df)

    assert result["damage"] == 111
    assert result["max_damage"] == 111
    assert result["min_damage"] == 94          # floor(111.6 * 0.85) = 94
    assert result["damage_percent"] == 111.0
    assert result["stab"] == 1.5
    assert result["type_modifier"] == 2.0
    assert result["ohko_chance"] == 62.5
    assert result["two_hko_chance"] == 100.0
    assert result["category"] == "physical"


def test_low_roll_uses_085(type_chart_df, battler, fixed_roll):
    fixed_roll(0.85)
    result = calculate_damage(battler(["fire"]), battler(["grass"], hp=100), move("fire"), type_chart_df)
    assert result["damage"] == result["min_damage"] == 94


def test_no_stab_neutral(type_chart_df, battler, fixed_roll):
    fixed_roll(1.0)
    # attacker không phải hệ normal, normal vs grass không có trong chart -> 1x; base 37.2
    result = calculate_damage(battler(["fire"]), battler(["grass"]), move("normal"), type_chart_df)
    assert (result["stab"], result["type_modifier"]) == (1, 1.0)
    assert result["max_damage"] == 37 and result["min_damage"] == 31


def test_special_move_uses_spatk_and_spdef(type_chart_df, battler, fixed_roll):
    fixed_roll(1.0)
    attacker = battler(["fire"], spatk=150)
    defender = battler(["grass"], spdef=100)
    # (22 * 80 * 150 / 100) / 50 + 2 = 54.8 ; water vs grass = 1x ; attacker không có STAB water
    result = calculate_damage(attacker, defender, move("water", damage_class="special"), type_chart_df)
    assert result["max_damage"] == 54
    assert result["category"] == "special"


def test_immune_target_takes_zero(type_chart_df, battler, fixed_roll):
    fixed_roll(1.0)
    result = calculate_damage(battler(["ground"]), battler(["flying"]), move("ground"), type_chart_df)
    assert result["damage"] == 0
    assert result["damage_percent"] == 0.0
    assert result["ohko_chance"] == 0.0
    assert result["type_modifier"] == 0.0


def test_random_roll_stays_within_min_max(type_chart_df, battler):
    attacker, defender = battler(["fire"]), battler(["grass"], hp=100)
    for _ in range(200):
        r = calculate_damage(attacker, defender, move("fire"), type_chart_df)
        assert r["min_damage"] <= r["damage"] <= r["max_damage"]


# ---------- KNOWN ISSUE ----------
@pytest.mark.xfail(
    strict=True,
    reason="STAB đang xét theo type gốc của move; move bị -ate đổi hệ (Pixilate) phải được STAB nếu user cùng hệ",
)
def test_pixilate_sylveon_gets_stab_on_converted_move(type_chart_df, battler, fixed_roll):
    fixed_roll(1.0)
    attacker = battler(["fairy"], ability="pixilate")
    result = calculate_damage(attacker, battler(["dragon"]), move("normal"), type_chart_df)
    assert result["stab"] == 1.5