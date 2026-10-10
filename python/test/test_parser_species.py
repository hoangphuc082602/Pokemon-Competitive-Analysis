import pytest

from parser.parser import BatchParser

LOG = """|j|☆alice
|j|☆bob
|player|p1|alice|1|1500
|player|p2|bob|2|1500
|gametype|doubles
|tier|[Gen 9] VGC 2024 Reg G
|rule|Species Clause: Limit one of each Pokémon
|poke|p1|Urshifu-*, L50|
|poke|p1|Tornadus, L50|
|poke|p2|Charizard, L50|
|poke|p2|Incineroar, L50|
|teampreview|4
|
|start
|switch|p1a: Urshifu|Urshifu-Rapid-Strike, L50, M|100/100
|switch|p1b: Teraclope!|Tornadus-Therian, L50, M|100/100
|switch|p2a: Charizard|Charizard, L50, M|100/100
|switch|p2b: Incineroar|Incineroar, L50, M|100/100
|turn|1
|move|p1a: Urshifu|Wicked Blow|p2a: Charizard
|-terastallize|p1b: Teraclope!|Flying
|-ability|p2b: Incineroar|Intimidate|boost
|-status|p2a: Charizard|brn
|detailschange|p2a: Charizard|Charizard-Mega-X, L50, M
|move|p2a: Charizard|Flare Blitz|p1a: Urshifu
|faint|p2a: Charizard
|turn|2
|switch|p1b: Teraclope!|Tornadus-Therian, L50, M|80/100
|win|alice
"""


@pytest.fixture(scope="module")
def parsed():
    return BatchParser().parse_text(LOG, battle_id="battle-test")


def test_leads_store_species_and_keep_nickname(parsed):
    leads = {(l.pokemon_name, l.species) for l in parsed.leads}
    assert ("Urshifu", "Urshifu-Rapid-Strike") in leads
    assert ("Teraclope!", "Tornadus-Therian") in leads


def test_midgame_switch_stores_species_for_a_nicknamed_pokemon(parsed):
    assert [(s.pokemon_name, s.species) for s in parsed.switches] == [("Teraclope!", "Tornadus-Therian")]


def test_move_tera_ability_status_faint_carry_species(parsed):
    assert parsed.moves[0].species == "Urshifu-Rapid-Strike"
    assert parsed.teras[0].species == "Tornadus-Therian"      # event only knows the nickname
    assert parsed.abilities[0].species == "Incineroar"
    assert parsed.statuses[0].species == "Charizard"          # before the Mega Evolution


def test_detailschange_updates_species_for_later_events(parsed):
    assert parsed.moves[1].species == "Charizard-Mega-X"
    assert parsed.faints[0].species == "Charizard-Mega-X"


def test_team_preview_slot_is_still_masked(parsed):
    names = {t.pokemon_name for t in parsed.team_slots}
    assert "Urshifu-*" in names