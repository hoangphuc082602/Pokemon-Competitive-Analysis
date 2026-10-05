from python.calculations.atk_balance import analyze_damage_profile


def test_counts_physical_and_special(moves_df):
    team = [
        {"moves": ["earthquake", "close-combat"]},   # 2 physical
        {"moves": ["thunderbolt", "hydro-pump"]},    # 2 special
    ]
    assert analyze_damage_profile(team, moves_df) == {"physical_moves": 2, "special_moves": 2}


def test_status_moves_are_not_counted(moves_df):
    team = [{"moves": ["protect", "earthquake"]}]
    assert analyze_damage_profile(team, moves_df) == {"physical_moves": 1, "special_moves": 0}


def test_unknown_moves_are_skipped(moves_df):
    team = [{"moves": ["not-a-real-move", "flamethrower"]}]
    assert analyze_damage_profile(team, moves_df) == {"physical_moves": 0, "special_moves": 1}


def test_empty_team(moves_df):
    assert analyze_damage_profile([], moves_df) == {"physical_moves": 0, "special_moves": 0}