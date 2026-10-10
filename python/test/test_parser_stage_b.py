import pytest

from parser.parser import BatchParser
from python.test.test_parser_species import LOG

LOG_B = (
    LOG.replace("|poke|p1|Tornadus, L50|", "|poke|p1|Tornadus-Therian, L50|\n|poke|p1|Rillaboom, L50|")
       .replace("|poke|p2|Incineroar, L50|", "|poke|p2|Incineroar, L50|\n|poke|p2|Zacian-*, L50|")
       .replace("|move|p1a: Urshifu|Wicked Blow|p2a: Charizard\n",
                "|move|p1a: Urshifu|Wicked Blow|p2a: Charizard\n|-damage|p2a: Charizard|0 fnt\n")
)


@pytest.fixture(scope="module")
def parsed():
    return BatchParser().parse_text(LOG_B, battle_id="battle-b")


def _slot(parsed, side, name):
    return next(t for t in parsed.team_slots if t.player_side == side and t.pokemon_name == name)


def test_masked_slot_is_resolved_from_the_species_that_entered_the_field(parsed):
    s = _slot(parsed, "p1", "Urshifu-*")
    assert (s.form_status, s.species_observed, s.was_sent_out) == ("observed", "Urshifu-Rapid-Strike", True)


def test_masked_slot_never_seen_is_unobserved(parsed):
    s = _slot(parsed, "p2", "Zacian-*")
    assert (s.form_status, s.species_observed, s.was_sent_out) == ("unobserved", "", False)


def test_nicknamed_lead_is_recognised_by_species(parsed):
    s = _slot(parsed, "p1", "Tornadus-Therian")          # nickname 'Teraclope!' in the battle
    assert s.is_lead and s.was_sent_out and s.form_status == "listed"


def test_unsent_pokemon_is_not_a_lead_and_not_sent_out(parsed):
    s = _slot(parsed, "p1", "Rillaboom")
    assert not s.is_lead and not s.was_sent_out


def test_two_forms_seen_for_one_masked_slot_is_ambiguous():
    log = LOG_B.replace("|turn|2\n", "|turn|2\n|switch|p2a: Zac|Zacian, L50|100/100\n|switch|p2b: Zac2|Zacian-Crowned, L50|100/100\n")
    s = _slot(BatchParser().parse_text(log, battle_id="b"), "p2", "Zacian-*")
    assert s.form_status == "ambiguous" and s.species_observed == ""


def test_damage_and_ko_carry_attacker_and_victim_species(parsed):
    d = parsed.damages[0]
    assert (d.attacker_species, d.defender_species) == ("Urshifu-Rapid-Strike", "Charizard")
    k = parsed.kos[0]
    assert (k.killer_species, k.victim_species) == ("Urshifu-Rapid-Strike", "Charizard")


def _parse(log):
    return BatchParser().parse_text(log, battle_id="b")


def test_repeated_player_lines_keep_one_row_per_side():
    log = LOG_B.replace("|player|p2|bob|2|1500\n",
                        "|player|p2|bob|2|1500\n|player|p1|alice|5\n|player|p1|\n|player|p2|bob|7|1511\n")
    sides = [(b.side, b.username) for b in _parse(log).battle_players]
    assert sorted(sides) == [("p1", "alice"), ("p2", "bob")]


def test_later_player_line_fills_a_missing_rating():
    log = LOG_B.replace("|player|p1|alice|1|1500", "|player|p1|alice|1\n|player|p1|alice|1|1620")
    rows = {b.side: b.rating_before for b in _parse(log).battle_players}
    assert rows["p1"] == 1620


def test_turn_zero_replacement_is_a_switch_not_a_third_lead():
    log = LOG_B.replace("|turn|1\n", "|switch|p1a: Sylveon|Sylveon, L50, F|100/100\n|turn|1\n", 1)
    parsed = _parse(log)
    p1_leads = [l for l in parsed.leads if l.username == "alice"]
    assert len(p1_leads) == 2
    assert any(s.species == "Sylveon" for s in parsed.switches)


def test_avatar_id_is_never_read_as_a_rating():
    log = LOG_B.replace("|player|p1|alice|1|1500", "|player|p1|alice|265|")
    rows = {b.side: b.rating_before for b in _parse(log).battle_players}
    assert rows["p1"] is None and rows["p2"] == 1500