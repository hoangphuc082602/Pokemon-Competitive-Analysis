import pandas as pd
import pytest

from python.analytics.partner_stats import build_partner_table, partners_of
from python.test.test_pokemon_usage import REG, _write

TEAMS = [  # battle, side, preview name
    ("b1", "p1", "Urshifu-*"), ("b1", "p1", "Incineroar"), ("b1", "p1", "Rillaboom"),      # wins, 1250
    ("b1", "p2", "Incineroar"), ("b1", "p2", "Rillaboom"),                                 # loses, no rating
    ("b2", "p1", "Urshifu-*"), ("b2", "p1", "Incineroar"), ("b2", "p1", "Miasmaw"),        # loses, 1600; Miasmaw unmapped
    ("b2", "p2", "Incineroar"), ("b2", "p2", "Rillaboom"), ("b2", "p2", "Arceus-Fire"),    # wins, 1100
    ("b3", "p1", "Incineroar"), ("b3", "p1", "Rillaboom"),                                 # other format
]


@pytest.fixture
def table(tmp_path):
    out, name_map = _write(tmp_path)
    slots = pd.DataFrame(TEAMS, columns=["battle_id", "player_side", "pokemon_name"])
    slots.to_parquet(out / "battle_team_slot.parquet", row_group_size=4)       # groups that cut battles in the middle
    extra = pd.DataFrame([("Rillaboom", 812, "rillaboom", 812, "exact", "known")],
                         columns=["showdown_name", "poke_id", "pokemon", "species_id", "method", "form_status"])
    return build_partner_table(out, pd.concat([name_map, extra], ignore_index=True), min_support=1)


def _pair(table, a, b, band="all"):
    sel = table[(table["species_a_id"] == a) & (table["species_b_id"] == b) & (table["rating_band"] == band)]
    return sel.iloc[0]


def test_pair_counts_and_wins_follow_the_team_side(table):
    t, _ = table
    inc_ril = _pair(t, 727, 812)
    assert (inc_ril["teams_both"], inc_ril["wins_both"]) == (3, 2)           # b1 p1 win, b1 p2 loss, b2 p2 win
    uru_inc = _pair(t, 727, 892)
    assert (uru_inc["teams_both"], uru_inc["wins_both"]) == (2, 1)           # b1 p1 win, b2 p1 loss


def test_unmapped_species_and_other_formats_are_excluded(table):
    t, avg = table
    assert t[(t["species_a_id"] == 493) | (t["species_b_id"] == 493)]["teams_both"].max() == 1   # only Arceus-Fire + 2 partners
    assert t[t["rating_band"] == "all"]["teams_both"].sum() == 3 + 2 + 1 + 1 + 1                   # 8 pair counts ...
    assert t[t["rating_band"] != "all"]["teams_both"].sum() == 8                                   # ... split over the bands


def test_lift_uses_team_counts_as_probabilities(table):
    t, _ = table
    r = _pair(t, 812, 892)          # Rillaboom with Urshifu: 1 team, Rillaboom on 3 teams, Urshifu on 2, 4 teams in total
    assert (r["teams_a"], r["teams_b"], r["teams_total"]) == (3, 2, 4)
    assert r["lift"] == pytest.approx(1 * 4 / (3 * 2))
    assert _pair(t, 727, 812)["lift"] == pytest.approx(1.0)


def test_each_team_counts_in_its_own_rating_band(table):
    t, _ = table
    assert _pair(t, 727, 812, "1200_1399")["teams_both"] == 1       # b1 p1 (1250)
    assert _pair(t, 727, 812, "unknown")["teams_both"] == 1         # b1 p2 (no rating)
    assert _pair(t, 727, 812, "below_1200")["teams_both"] == 1      # b2 p2 (1100)


def test_min_support_drops_rare_pairs(tmp_path):
    out, name_map = _write(tmp_path)
    pd.DataFrame(TEAMS, columns=["battle_id", "player_side", "pokemon_name"]).to_parquet(out / "battle_team_slot.parquet")
    extra = pd.DataFrame([("Rillaboom", 812, "rillaboom", 812, "exact", "known")],
                         columns=["showdown_name", "poke_id", "pokemon", "species_id", "method", "form_status"])
    t, _ = build_partner_table(out, pd.concat([name_map, extra], ignore_index=True), min_support=3)
    assert set(zip(t["species_a_id"], t["species_b_id"])) == {(727, 812)}


def test_partners_of_lists_the_other_species(table):
    t, _ = table
    p = partners_of(t, "Incineroar", REG).set_index("partner")
    assert p.loc["Rillaboom", "teams_both"] == 3 and p.loc["Rillaboom", "share_%"] == 75.0