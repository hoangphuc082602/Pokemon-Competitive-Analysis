import pandas as pd
import pytest

from python.analytics.pokemon_usage import build_tables
from python.analytics.tera_stats import build_tera_tables, top_tera
from python.test.test_pokemon_usage import REG, _write

TERA = [  # battle, owner, species at the time, tera type
    ("b1", "alice", "Urshifu-Rapid-Strike", "Dark"),
    ("b1", "alice", "Urshifu-Rapid-Strike", "Water"),     # second event for the same player and battle: ignored
    ("b2", "dave", "Urshifu", "Fire"),
    ("b2", "carol", "Arceus-Fire", "Fire"),
    ("b1", "zed", "Incineroar", "Water"),                 # not a player of b1
    ("b1", "bob", "Miasmaw", "Ghost"),                    # species not in the mapping
    ("b3", "eve", "Incineroar", "Grass"),                 # other format
]


@pytest.fixture
def tera(tmp_path):
    out, name_map = _write(tmp_path)
    pd.DataFrame(TERA, columns=["battle_id", "username", "species", "tera_type"]).to_parquet(out / "battle_tera.parquet")
    usage, _, _ = build_tables(out, name_map)
    return build_tera_tables(out, usage, name_map, batch_size=2)


def _summary(summary, species_id, band="all"):
    return summary[(summary["species_id"] == species_id) & (summary["rating_band"] == band)].iloc[0]


def test_events_are_attributed_deduplicated_and_filtered(tera):
    summary, types, unmapped, unattributed = tera
    assert (unmapped, unattributed) == (1, 1)
    assert _summary(summary, 892)["tera_events"] == 2          # alice (once) and dave
    assert _summary(summary, 727)["tera_events"] == 0          # the Incineroar events were not valid


def test_rates_use_sent_out_as_denominator(tera):
    summary, _, _, _ = tera
    uru = _summary(summary, 892)
    assert (uru["sent_out"], uru["tera_events"], uru["tera_rate"]) == (2, 2, 1.0)
    inc = _summary(summary, 727)
    assert inc["tera_rate"] == 0.0 and inc["win_rate_no_tera"] == 1.0 and pd.isna(inc["win_rate_tera"])


def test_win_rate_with_tera_follows_the_owner_side(tera):
    summary, _, _, _ = tera
    assert _summary(summary, 892)["win_rate_tera"] == 1.0       # alice (p1) and dave (p2) both won
    assert _summary(summary, 493)["win_rate_tera"] == 0.0       # carol lost


def test_type_shares_add_up_to_one_per_species(tera):
    _, types, _, _ = tera
    uru = types[(types["species_id"] == 892) & (types["rating_band"] == "all")]
    assert dict(zip(uru["tera_type"], uru["type_share"])) == {"Dark": 0.5, "Fire": 0.5}


def test_each_player_is_banded_by_their_own_rating(tera):
    summary, _, _, _ = tera
    assert _summary(summary, 892, "1200_1399")["tera_events"] == 1      # alice, 1250
    assert _summary(summary, 892, "below_1200")["tera_events"] == 1     # dave, 1100
    assert _summary(summary, 493, "1500_plus")["tera_events"] == 1      # carol, 1600


def test_top_tera_reports_the_most_used_type(tera):
    summary, types, _, _ = tera
    top = top_tera(summary, types, REG).set_index("species")
    assert top.loc["Urshifu", "tera_events"] == 2 and top.loc["Urshifu", "tera_%"] == 100.0
    assert top.loc["Arceus-Fire", "top_type"] == "Fire"