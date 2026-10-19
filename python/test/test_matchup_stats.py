import pandas as pd
import pytest

from python.analytics.matchup_stats import build_matchup_table, is_antisymmetric, opponents_of
from python.test.test_partner_stats import TEAMS
from python.test.test_pokemon_usage import REG, _write


@pytest.fixture
def table(tmp_path):
    out, name_map = _write(tmp_path)
    pd.DataFrame(TEAMS, columns=["battle_id", "player_side", "pokemon_name"]).to_parquet(out / "battle_team_slot.parquet", row_group_size=4)
    extra = pd.DataFrame([("Rillaboom", 812, "rillaboom", 812, "exact", "known")], columns=name_map.columns)
    return build_matchup_table(out, pd.concat([name_map, extra], ignore_index=True), min_support=1)


def _row(t, a, b, band="all"):
    return t[(t["species_a_id"] == a) & (t["species_b_id"] == b) & (t["rating_band"] == band)].iloc[0]


def test_observations_are_teams_with_a_against_teams_with_b(table):
    r = _row(table, 892, 727)                  # Urshifu team vs Incineroar team: b1 (Urshifu side won), b2 (lost)
    assert (r["battles"], r["wins"]) == (2, 1)
    r = _row(table, 727, 812)                  # Incineroar team vs Rillaboom team: b1 p1 won, b1 p2 lost, b2 p1 lost
    assert (r["battles"], r["wins"]) == (3, 1)


def test_the_table_is_antisymmetric(table):
    ab, ba = _row(table, 812, 727), _row(table, 727, 812)
    assert ab["battles"] == ba["battles"] == 3 and ab["wins"] + ba["wins"] == 3
    assert is_antisymmetric(table)


def test_the_same_species_on_both_teams_is_not_a_matchup(table):
    assert not ((table["species_a_id"] == table["species_b_id"]).any())


def test_delta_compares_with_the_species_overall_win_rate(table):
    r = _row(table, 727, 812)
    assert r["a_win_rate"] == pytest.approx(0.5)               # Incineroar teams: 2 wins in 4
    assert r["win_rate_delta"] == pytest.approx(1 / 3 - 0.5)


def test_other_formats_and_unmapped_species_are_excluded(table):
    a = table[table["rating_band"] == "all"]
    assert a["battles"].sum() == 2 + 2 + 2 + 2 + 3 + 3 + 1 + 1 + 1 + 1          # 18 ordered observations from b1 and b2 only
    assert a["wins"].sum() * 2 == a["battles"].sum()                             # every observation has a mirrored loss
    assert set(a["species_a_id"]) <= {727, 812, 892, 493}                         # Miasmaw (unmapped) never appears


def test_each_observation_uses_the_rating_band_of_the_player_of_a(table):
    assert _row(table, 812, 727, "unknown")["battles"] == 1          # b1 p2, no rating
    assert _row(table, 892, 727, "1200_1399")["battles"] == 1        # b1 p1 (1250)
    assert _row(table, 892, 727, "1500_plus")["battles"] == 1        # b2 p1 (1600)


def test_min_support_and_opponent_lists(tmp_path):
    out, name_map = _write(tmp_path)
    pd.DataFrame(TEAMS, columns=["battle_id", "player_side", "pokemon_name"]).to_parquet(out / "battle_team_slot.parquet")
    extra = pd.DataFrame([("Rillaboom", 812, "rillaboom", 812, "exact", "known")], columns=name_map.columns)
    nm = pd.concat([name_map, extra], ignore_index=True)
    t = build_matchup_table(out, nm, min_support=3)
    assert set(zip(t[t["rating_band"] == "all"]["species_a_id"], t[t["rating_band"] == "all"]["species_b_id"])) == {(727, 812), (812, 727)}
    hard, easy = opponents_of(build_matchup_table(out, nm, min_support=1), "Incineroar", REG, min_battles=1, n=2)
    assert len(hard) == 2 and len(easy) == 2
    assert hard["z"].iloc[0] <= easy["z"].iloc[0]


def test_expected_win_rate_combines_both_teams_overall_strength(table):
    r = _row(table, 727, 812)          # Incineroar teams win 2 of 4; Rillaboom teams win 2 of 3
    assert r["a_win_rate"] == pytest.approx(0.5) and r["b_win_rate"] == pytest.approx(2 / 3)
    assert r["expected_win_rate"] == pytest.approx(1 / 3)           # log5: the stronger opponent is expected to win
    assert r["win_rate_vs_expected"] == pytest.approx(0.0, abs=1e-9)   # observed 1 win in 3 is exactly that


def test_a_weak_opponent_is_not_counted_as_an_easy_matchup_by_itself(table):
    r = _row(table, 812, 727)          # Rillaboom teams (2/3) against Incineroar teams (2/4): expected above 50%
    assert r["expected_win_rate"] > 0.5
    assert r["win_rate_vs_expected"] == pytest.approx(r["win_rate"] - r["expected_win_rate"])