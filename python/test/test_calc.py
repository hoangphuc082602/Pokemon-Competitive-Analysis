import pytest

from python.calculations.nature_calc import get_nature_modifiers
from python.calculations.stats_calc import (
    calculate_final_stats,
    calculate_hp,
    calculate_other_stat,
)


# Giá trị tham chiếu: base stat thật của Incineroar / Flutter Mane ở Level 50.
def test_hp_level50_zero_ev():
    # (2*95 + 31 + 0) * 50 / 100 = 110.5 -> 110, + 50 + 10
    assert calculate_hp(95, 31, 0, 50) == 170


def test_hp_level50_max_ev():
    # (2*95 + 31 + 63) * 50 / 100 = 142 -> 142 + 60
    assert calculate_hp(95, 31, 252, 50) == 202


def test_other_stat_neutral_nature():
    # Flutter Mane Speed 135, 252 EV, trung tính: floor(182) + 5
    assert calculate_other_stat(135, 31, 252, 50, 1.0) == 187


def test_other_stat_positive_nature():
    # 187 * 1.1 = 205.7 -> 205 (Timid, 252 Spe)
    assert calculate_other_stat(135, 31, 252, 50, 1.1) == 205


def test_other_stat_negative_nature():
    # Flutter Mane Atk 55, 0 EV, IV 0, nature giảm: floor(55*2*50/100)=55 +5 = 60 -> 60*0.9 = 54
    assert calculate_other_stat(55, 0, 0, 50, 0.9) == 54


def test_nature_modifiers_timid(nature_df):
    mods = get_nature_modifiers(nature_df, "Timid")  # không phân biệt hoa/thường
    assert mods["spe"] == pytest.approx(1.1)
    assert mods["atk"] == pytest.approx(0.9)
    assert mods["def"] == mods["spatk"] == mods["spdef"] == 1.0


def test_nature_modifiers_neutral_and_unknown(nature_df):
    neutral = {"atk": 1.0, "def": 1.0, "spatk": 1.0, "spdef": 1.0, "spe": 1.0}
    assert get_nature_modifiers(nature_df, "hardy") == neutral
    assert get_nature_modifiers(nature_df, "no-such-nature") == neutral


def test_final_stats_flutter_mane_timid():
    base = {"hp": 55, "atk": 55, "def": 55, "spatk": 135, "spdef": 135, "spe": 135}
    ivs = dict.fromkeys(base, 31)
    evs = {"hp": 4, "atk": 0, "def": 0, "spatk": 252, "spdef": 0, "spe": 252}
    mods = {"atk": 0.9, "def": 1.0, "spatk": 1.0, "spdef": 1.0, "spe": 1.1}

    assert calculate_final_stats(base, ivs, evs, 50, mods) == {
        "hp": 131,      # (110+31+1)*50//100 = 71, +60
        "atk": 67,      # (110+31)*50//100 = 70, +5 = 75, *0.9 = 67.5 -> 67
        "def": 75,
        "spatk": 187,   # (270+31+63)*50//100 = 182, +5
        "spdef": 155,   # (270+31)*50//100 = 150, +5
        "spe": 205,     # 187 * 1.1 = 205.7 -> 205
    }