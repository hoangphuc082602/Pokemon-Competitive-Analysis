import pandas as pd
import pytest

from python.analytics.pokemon_usage import build_tables, rating_band, species_labels, top_species, wilson

REG = "gen9vgc2024regg"


def _write(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    pd.DataFrame({
        "battle_id": ["b1", "b2", "b3", "b4", "b5"],
        "format_id": [REG, REG + "(bo3)", "gen9doublesou", REG, REG],
        "turn_count": [5, 3, 4, 0, 4],
        "upload_time": [1704110400, 1706788800, 1706788800, 1706788800, 1706788800],      # 2024-01-01 / 2024-02-01 12:00 UTC
    }).to_parquet(out / "battle.parquet")
    players = [("b1", "p1", "WIN", 1250.0, "alice"), ("b1", "p2", "LOSS", None, "bob"),
               ("b2", "p1", "LOSS", 1600.0, "carol"), ("b2", "p2", "WIN", 1100.0, "dave"),
               ("b3", "p1", "WIN", 1500.0, "eve"), ("b3", "p2", "LOSS", 1500.0, "fay"),
               ("b4", "p1", "WIN", 1300.0, "gus"), ("b4", "p2", "LOSS", 1300.0, "hal"),
               ("b5", "p1", None, 1300.0, "ivy"), ("b5", "p2", None, 1300.0, "jon")]
    pd.DataFrame(players, columns=["battle_id", "side", "result", "rating_before", "username"]).to_parquet(out / "battle_players.parquet")
    slots = [  # battle, side, preview name, observed form, form_status, sent_out, lead
        ("b1", "p1", "Urshifu-*", "Urshifu-Rapid-Strike", "observed", 1, 1),
        ("b1", "p1", "Incineroar", "Incineroar", "listed", 1, 0),
        ("b1", "p2", "Urshifu-*", "", "unobserved", 0, 0),
        ("b2", "p2", "Urshifu-*", "Urshifu", "observed", 1, 1),
        ("b2", "p1", "Arceus-Fire", "Arceus-Fire", "listed", 1, 1),
        ("b2", "p1", "Miasmaw", "Miasmaw", "listed", 1, 0),          # not in the mapping
        ("b3", "p1", "Incineroar", "Incineroar", "listed", 1, 1),    # other format
        ("b4", "p1", "Incineroar", "Incineroar", "listed", 1, 1),    # no turns
        ("b5", "p1", "Incineroar", "Incineroar", "listed", 1, 1),    # no winner
    ]
    pd.DataFrame(slots, columns=["battle_id", "player_side", "pokemon_name", "species_observed", "form_status",
                                 "was_sent_out", "is_lead"]).to_parquet(out / "battle_team_slot.parquet")
    name_map = pd.DataFrame([
        ("Urshifu-*", None, None, 892, "masked", "masked"),
        ("Urshifu-Rapid-Strike", 10191, "urshifu-rapid-strike", 892, "exact", "known"),
        ("Urshifu", 892, "urshifu-single-strike", 892, "override", "known"),
        ("Incineroar", 727, "incineroar", 727, "exact", "known"),
        ("Arceus-Fire", None, None, 493, "unlisted", "unlisted"),
    ], columns=["showdown_name", "poke_id", "pokemon", "species_id", "method", "form_status"])
    return out, name_map


@pytest.fixture
def tables(tmp_path):
    out, name_map = _write(tmp_path)
    return build_tables(out, name_map, batch_size=3)     # tiny batches: exercises the streaming path


def _row(usage, species_id, poke_id, basis, band="all"):
    sel = usage[(usage["species_id"] == species_id) & (usage["form_basis"] == basis) & (usage["rating_band"] == band)]
    sel = sel[sel["poke_id"].isna()] if poke_id is None else sel[sel["poke_id"] == poke_id]
    return sel.iloc[0]


def test_scope_keeps_only_completed_vgc_battles(tables):
    usage, totals, _ = tables
    assert totals[totals["rating_band"] == "all"].to_dict("records") == [
        {"regulation": REG, "rating_band": "all", "battles": 2, "player_battles": 4}]
    assert usage[usage["rating_band"] == "all"]["appearances"].sum() == 5        # b1 (3 slots) + b2 (2 mapped slots); b3-b5 excluded, Miasmaw dropped


def test_masked_family_is_split_by_form_basis(tables):
    usage, _, _ = tables
    rapid = _row(usage, 892, 10191, "observed")
    assert (rapid["appearances"], rapid["wins"], rapid["sent_out"], rapid["leads"]) == (1, 1, 1, 1)
    single = _row(usage, 892, 892, "observed")
    assert (single["appearances"], single["wins"]) == (1, 1)             # b2: p2 won
    unknown = _row(usage, 892, None, "unobserved")
    assert (unknown["appearances"], unknown["wins"], unknown["sent_out"]) == (1, 0, 0)


def test_species_only_form_keeps_species_without_a_guessed_form(tables):
    usage, _, _ = tables
    arc = _row(usage, 493, None, "species_only")
    assert (arc["appearances"], arc["wins"]) == (1, 0)                   # b2: p1 lost


def test_unmapped_names_are_counted_not_silently_lost(tables):
    assert tables[2] == 1


def test_denominator_and_rates_are_stored_with_the_row(tables):
    usage, _, _ = tables
    inc = _row(usage, 727, 727, "listed")
    assert inc["player_battles"] == 4 and inc["usage_share"] == 0.25
    assert inc["win_rate"] == 1.0 and inc["win_ci_low"] < 1.0 <= inc["win_ci_high"] + 1e-9


def test_wilson_interval_matches_the_known_value():
    lo, hi = wilson(pd.Series([50]), pd.Series([100]))
    assert lo[0] == pytest.approx(0.4038, abs=1e-3) and hi[0] == pytest.approx(0.5962, abs=1e-3)


def test_species_label_is_the_shortest_showdown_name_without_the_mask(tmp_path):
    _, name_map = _write(tmp_path)
    labels = species_labels(name_map)
    assert labels[892] == "Urshifu" and labels[727] == "Incineroar" and labels[493] == "Arceus-Fire"


def test_usage_rows_carry_readable_species_and_form(tables):
    usage, _, _ = tables
    rapid = _row(usage, 892, 10191, "observed")
    assert (rapid["species"], rapid["form"]) == ("Urshifu", "urshifu-rapid-strike")
    assert pd.isna(_row(usage, 892, None, "unobserved")["form"])


def test_top_species_merges_forms_and_reports_percentages(tables):
    usage, _, _ = tables
    top = top_species(usage, REG).set_index("species")
    assert top.loc["Urshifu", "appearances"] == 3 and top.loc["Urshifu", "usage_%"] == 75.0
    assert top.loc["Urshifu", "win_%"] == 66.7


def test_rating_band_edges_and_unknown():
    r = rating_band([1199.9, 1200, 1399.9, 1400, 1499, 1500, 1900, None])
    assert list(r) == ["below_1200", "1200_1399", "1200_1399", "1400_1499", "1400_1499", "1500_plus", "1500_plus", "unknown"]


def test_each_player_is_banded_by_their_own_rating(tables):
    usage, totals, _ = tables
    assert _row(usage, 892, 10191, "observed", "1200_1399")["appearances"] == 1      # b1 p1, 1250
    assert _row(usage, 892, 892, "observed", "below_1200")["appearances"] == 1       # b2 p2, 1100
    assert _row(usage, 892, None, "unobserved", "unknown")["appearances"] == 1       # b1 p2, no rating
    assert _row(usage, 493, None, "species_only", "1500_plus")["appearances"] == 1   # b2 p1, 1600
    per_band = totals[totals["rating_band"] != "all"].set_index("rating_band")["player_battles"].to_dict()
    assert per_band == {"below_1200": 1, "1200_1399": 1, "1500_plus": 1, "unknown": 1}


def test_band_rows_add_up_to_the_all_rows(tables):
    usage, _, _ = tables
    for col in ("appearances", "wins", "sent_out", "leads"):
        assert usage[usage["rating_band"] == "all"][col].sum() == usage[usage["rating_band"] != "all"][col].sum()


def test_top_species_can_be_filtered_by_band(tables):
    usage, _, _ = tables
    top = top_species(usage, REG, band="unknown")
    assert list(top["species"]) == ["Urshifu"] and top.iloc[0]["usage_%"] == 100.0


def test_win_rate_is_also_given_relative_to_the_band_baseline(tables):
    usage, _, _ = tables
    inc = _row(usage, 727, 727, "listed")
    assert inc["band_win_rate"] == pytest.approx(0.6)          # 3 wins in 5 slots of this regulation and band
    assert inc["win_rate_delta"] == pytest.approx(0.4)


def test_sent_out_wins_counts_only_wins_of_pokemon_that_entered_the_field(tables):
    usage, _, _ = tables
    rapid = _row(usage, 892, 10191, "observed")
    assert (rapid["sent_out"], rapid["sent_out_wins"]) == (1, 1)
    unknown = _row(usage, 892, None, "unobserved")
    assert (unknown["sent_out"], unknown["sent_out_wins"]) == (0, 0)