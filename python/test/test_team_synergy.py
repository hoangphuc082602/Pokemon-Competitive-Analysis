from python.calculations.team_synergy import analyze_role_distribution, calculate_team_synergy


def mon(**stats):
    base = {"atk": 100, "spatk": 100, "def": 100, "spdef": 100, "spe": 100}
    base.update(stats)
    return {"stats": base}


def test_role_distribution_counts_each_role():
    team = [mon(atk=180, spe=160), mon(atk=180, spe=160), mon(spdef=160), mon()]
    assert analyze_role_distribution(team) == {"physical_sweeper": 2, "wall": 1, "balanced": 1}


def test_role_distribution_empty_team():
    assert analyze_role_distribution([]) == {}


def test_synergy_score_is_resistances_minus_weaknesses():
    assert calculate_team_synergy({"fire": 2, "water": 1}, {"grass": 4}) == 1
    assert calculate_team_synergy({"fire": 5}, {}) == -5