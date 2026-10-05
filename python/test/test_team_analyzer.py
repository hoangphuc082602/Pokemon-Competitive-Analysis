"""Test phân tích team (type_v2).

Scenario được port từ test cũ nhắm vào `team_type_analyzer.py` (module trùng lặp, gọi DB lúc import,
dự kiến xóa ở task #6). Logic canonical hiện tại nằm ở `type_v2.py`.
"""
from python.calculations.type_v2 import analyze_team_offense, resolve_move_types


def mon(name, moves, ability="none"):
    return {"pokemon": name, "moves": moves, "ability": ability}


# ---------- resolve_move_types ----------
def test_resolve_plain_moves(moves_df):
    assert resolve_move_types(moves_df, mon("x", ["thunderbolt", "earthquake"])) == ["electric", "ground"]


def test_resolve_skips_unknown_moves(moves_df):
    assert resolve_move_types(moves_df, mon("x", ["nope", "flamethrower"])) == ["fire"]


def test_pixilate_only_converts_normal_moves(moves_df):
    moves = ["hyper-voice", "flamethrower"]
    assert resolve_move_types(moves_df, mon("x", moves, "pixilate")) == ["fairy", "fire"]


def test_attacker_ability_display_name(moves_df):
    assert resolve_move_types(moves_df, mon("x", ["hyper-voice"], "Pixilate")) == ["fairy"]


def test_normalize_converts_every_move(moves_df):
    # type_v2 xử lý ĐÚNG; type_calc.get_actual_move_type thì chưa (xem xfail ở test_type_calc.py).
    assert resolve_move_types(moves_df, mon("x", ["flamethrower", "earthquake"], "normalize")) == ["normal", "normal"]


# ---------- analyze_team_offense ----------
def test_team_offense_coverage(type_chart_df, moves_df):
    team = [
        mon("rotom-wash", ["thunderbolt", "hydro-pump"]),   # electric->water,flying ; water->fire
        mon("garchomp", ["earthquake"]),                     # ground->fire,electric
    ]
    report = analyze_team_offense(type_chart_df, moves_df, team)

    assert report["by_pokemon"]["rotom-wash"]["flying"] is True
    assert report["by_pokemon"]["garchomp"]["flying"] is False

    electric = report["by_type"]["electric"]
    assert electric["can_hit"] == ["garchomp"] and electric["cannot_hit"] == ["rotom-wash"]

    fire = report["by_type"]["fire"]
    assert fire["coverage_count"] == 2 and fire["is_covered"]

    summary = report["summary"]
    assert summary["covered_types"] == ["electric", "fire", "flying", "water"]
    assert summary["not_covered_types"] == ["fairy", "fighting", "ghost", "ground", "normal"]
    assert (summary["coverage_count"], summary["not_covered_count"]) == (4, 5)


def test_team_offense_without_moves_covers_nothing(type_chart_df, moves_df):
    report = analyze_team_offense(type_chart_df, moves_df, [mon("blank", [])])
    assert report["summary"]["covered_types"] == []