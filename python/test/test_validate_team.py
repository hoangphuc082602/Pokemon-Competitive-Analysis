import pandas as pd
import pytest

from python.calculations.validate_moves import (
    check_duplicate_items,
    check_duplicate_pokemon,
    validate_moves,
    validate_team,
)


def mon(name, item, moves=()):
    return {"name": name, "item": item, "moves": list(moves)}


@pytest.fixture
def learnset_df():
    return pd.DataFrame(
        [
            ("garchomp", "earthquake"),
            ("garchomp", "dragon-claw"),
            ("incineroar", "fake-out"),
            ("incineroar", "flare-blitz"),
        ],
        columns=["pokemon", "move"],
    )


def test_duplicate_items():
    team = [mon("a", "leftovers"), mon("b", "choice-scarf"), mon("c", "leftovers")]
    assert check_duplicate_items(team) == ["leftovers"]


def test_duplicate_pokemon():
    team = [mon("garchomp", "x"), mon("incineroar", "y"), mon("garchomp", "z")]
    assert check_duplicate_pokemon(team) == ["garchomp"]


def test_no_duplicates():
    team = [mon("a", "x"), mon("b", "y")]
    assert check_duplicate_items(team) == [] and check_duplicate_pokemon(team) == []


def test_illegal_moves_are_reported(learnset_df):
    team = [mon("garchomp", "x", ["earthquake", "fake-out"])]
    assert validate_moves(team, learnset_df) == [{"pokemon": "garchomp", "move": "fake-out"}]


def test_valid_team(learnset_df):
    team = [mon("garchomp", "choice-scarf", ["earthquake"]), mon("incineroar", "sitrus-berry", ["fake-out"])]
    result = validate_team(team, learnset_df)
    assert result == {"duplicate_items": [], "duplicate_pokemon": [], "illegal_moves": [], "valid": True}


def test_invalid_team_reports_every_problem(learnset_df):
    team = [
        mon("garchomp", "leftovers", ["earthquake", "fake-out"]),
        mon("garchomp", "leftovers", ["dragon-claw"]),
    ]
    result = validate_team(team, learnset_df)
    assert result["valid"] is False
    assert result["duplicate_items"] == ["leftovers"]
    assert result["duplicate_pokemon"] == ["garchomp"]
    assert result["illegal_moves"] == [{"pokemon": "garchomp", "move": "fake-out"}]