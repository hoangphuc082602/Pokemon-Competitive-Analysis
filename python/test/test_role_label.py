import pytest

from python.calculations.role_label import label_role


def mon(atk=100, spatk=100, defense=100, spdef=100, spe=100):
    return {"stats": {"atk": atk, "spatk": spatk, "def": defense, "spdef": spdef, "spe": spe}}


def test_physical_sweeper():
    assert label_role(mon(atk=170, spe=150)) == "physical_sweeper"


def test_special_sweeper():
    assert label_role(mon(spatk=170, spe=150)) == "special_sweeper"


@pytest.mark.parametrize("stats", [dict(atk=169, spe=150), dict(atk=170, spe=149)])
def test_sweeper_thresholds_are_inclusive_boundaries(stats):
    assert label_role(mon(**stats)) == "balanced"


@pytest.mark.parametrize("stats", [dict(defense=150), dict(spdef=150)])
def test_wall(stats):
    assert label_role(mon(**stats)) == "wall"


def test_balanced_default():
    assert label_role(mon()) == "balanced"


def test_sweeper_takes_priority_over_wall():
    assert label_role(mon(atk=180, spe=160, defense=160)) == "physical_sweeper"


def test_physical_checked_before_special():
    # Hành vi hiện tại: đủ điều kiện cả hai thì trả về physical
    assert label_role(mon(atk=170, spatk=170, spe=150)) == "physical_sweeper"