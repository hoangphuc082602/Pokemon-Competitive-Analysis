import pandas as pd
import pytest

from python.analytics.usage_trend import build_trend_tables, species_trend
from python.test.test_pokemon_usage import REG, _write


@pytest.fixture
def trend(tmp_path):
    out, name_map = _write(tmp_path)
    return build_trend_tables(out, name_map)


def _row(usage, species_id, month, band="all"):
    sel = usage[(usage["species_id"] == species_id) & (usage["month"] == month) & (usage["rating_band"] == band)]
    return sel.iloc[0]


def test_each_battle_is_counted_in_its_upload_month(trend):
    usage, totals = trend
    totals = totals[totals["rating_band"] == "all"]
    assert totals[["regulation", "month", "battles", "player_battles"]].to_dict("records") == [
        {"regulation": REG, "month": "2024-01", "battles": 1, "player_battles": 2},       # b1
        {"regulation": REG, "month": "2024-02", "battles": 1, "player_battles": 2},       # b2 (b3-b5 are out of scope)
    ]
    assert _row(usage, 727, "2024-01")["appearances"] == 1                                # Incineroar on b1 p1


def test_denominator_is_the_month_not_the_regulation(trend):
    usage, _ = trend
    r = _row(usage, 892, "2024-01")             # Urshifu: both teams of b1 (masked names)
    assert (r["appearances"], r["player_battles"], r["usage_share"]) == (2, 2, 1.0)
    assert _row(usage, 892, "2024-02")["usage_share"] == 0.5     # only b2 p2 has Urshifu


def test_wins_follow_the_team_side(trend):
    usage, _ = trend
    assert _row(usage, 892, "2024-01")["wins"] == 1     # p1 won, p2 lost
    assert _row(usage, 892, "2024-02")["wins"] == 1     # p2 won


def test_species_trend_lists_months_in_order(trend):
    usage, _ = trend
    t = species_trend(usage, "Urshifu", REG)
    assert list(t["month"]) == ["2024-01", "2024-02"] and list(t["usage_%"]) == [100.0, 50.0]


def test_missing_upload_time_goes_to_an_unknown_month(tmp_path):
    out, name_map = _write(tmp_path)
    battle = pd.read_parquet(out / "battle.parquet")
    battle["upload_time"] = battle["upload_time"].astype("float")
    battle.loc[battle["battle_id"] == "b2", "upload_time"] = float("nan")
    battle.to_parquet(out / "battle.parquet")
    _, totals = build_trend_tables(out, name_map)
    assert set(totals["month"]) == {"2024-01", "unknown"}


def test_months_far_below_the_busiest_one_are_flagged_as_tail(tmp_path):
    out, name_map = _write(tmp_path)
    battle = pd.read_parquet(out / "battle.parquet")
    extra = pd.DataFrame({"battle_id": [f"x{i}" for i in range(40)], "format_id": REG, "turn_count": 5,
                          "upload_time": 1704110400})                 # 40 more battles in 2024-01
    pd.concat([battle, extra], ignore_index=True).to_parquet(out / "battle.parquet")
    players = pd.read_parquet(out / "battle_players.parquet")
    rows = [(f"x{i}", side, res, 1300.0, f"u{i}{side}") for i in range(40) for side, res in (("p1", "WIN"), ("p2", "LOSS"))]
    pd.concat([players, pd.DataFrame(rows, columns=players.columns)], ignore_index=True).to_parquet(out / "battle_players.parquet")
    usage, totals = build_trend_tables(out, name_map)
    a = totals[totals["rating_band"] == "all"]
    flags = dict(zip(a["month"], a["tail"]))
    assert flags == {"2024-01": False, "2024-02": True}                 # 2 battles vs 41: 4.9% of the peak
    assert usage[usage["month"] == "2024-02"]["tail"].all()
    band = totals[(totals["month"] == "2024-02") & (totals["rating_band"] != "all")]
    assert len(band) and band["tail"].all()                             # tail is a regulation-month flag, every band


def test_each_player_counts_in_the_band_of_their_own_rating(trend):
    usage, totals = trend
    t = totals[totals["month"] == "2024-01"].set_index("rating_band")["player_battles"].to_dict()
    assert t == {"all": 2, "1200_1399": 1, "unknown": 1}                 # b1: p1 1250, p2 no rating
    r = _row(usage, 892, "2024-01", "1200_1399")                         # Urshifu on b1 p1 (won)
    assert (r["appearances"], r["wins"], r["player_battles"], r["usage_share"]) == (1, 1, 1, 1.0)
    assert _row(usage, 892, "2024-02", "below_1200")["wins"] == 1        # b2 p2 (1100) won


def test_band_rows_add_up_to_the_all_rows(trend):
    usage, _ = trend
    bands = usage[usage["rating_band"] != "all"].groupby(["month", "species_id"])["appearances"].sum()
    every = usage[usage["rating_band"] == "all"].set_index(["month", "species_id"])["appearances"]
    assert bands.sort_index().to_dict() == every.sort_index().to_dict()