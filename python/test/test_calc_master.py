"""Damage-calc master data export (#16, #37): only the forms of the species dimension (species_forms.json), a
learnset per game (PokéAPI version group) of the exported regulations, each with its source. Seam:
calc_master.build(master_dir, forms, regulations) -> dict."""
import json

import pandas as pd
import pytest

from python.analytics.calc_master import CalcMasterError, build, main, read_regulations
from python.analytics.regulation_sources import UnmappedRegulationError

SV, CH = "scarlet-violet", "champions"
MOVE_COLUMNS = ["pokemon_id", "move_id", "learn_method", "level_learned"]


def _csv(master, name, columns, rows):
    pd.DataFrame(rows, columns=columns).to_csv(master / name, index=False)


def _add(master, name, rows):
    df = pd.read_csv(master / name)
    pd.concat([df, pd.DataFrame(rows, columns=df.columns)]).to_csv(master / name, index=False)


@pytest.fixture
def master(tmp_path):
    """Synthetic PokéAPI CSVs in the crawl_data layout. Charizard (6) and Calyrex-Shadow (10194, form of 898) are in
    the species dimension; Pikachu (25) is not. Champions teaches Charizard Flare Blitz, Scarlet / Violet does not."""
    m = tmp_path / "raw"
    m.mkdir()
    _csv(m, "stats_raw.csv", ["poke_id", "pokemon", "species_id", "hp", "atk", "def", "spatk", "spdef", "spe"],
         [(6, "charizard", 6, 78, 84, 78, 109, 85, 100), (25, "pikachu", 25, 35, 55, 40, 50, 50, 90),
          (898, "calyrex", 898, 100, 80, 80, 80, 80, 80), (10194, "calyrex-shadow", 898, 100, 85, 80, 165, 100, 150),
          (10034, "charizard-mega-x", 6, 78, 130, 111, 130, 85, 100)])
    _csv(m, "data_type.csv", ["type_id", "type"], [(1, "normal"), (8, "ghost"), (10, "fire"), (13, "electric")])
    _csv(m, "type_effectiveness.csv", ["attack_type_id", "defense_type_id", "multiplier"],
         [(1, 8, 0.0), (10, 10, 0.5), (8, 8, 2.0)])
    _csv(m, "ability_raw.csv", ["ability_id", "ability_name", "effect"],
         [(66, "blaze", "x"), (94, "solar-power", "x"), (9, "static", "x"), (127, "unnerve", "x"), (266, "as-one-spectrier", "x")])
    _csv(m, "pokemon_ability.csv", ["pokemon_id", "abi_id", "hidden_abi"],
         [(6, 66, False), (6, 94, True), (25, 9, False), (898, 127, False)])   # no rows for the form 10194
    _csv(m, "data_damage_class.csv", ["damage_class_id", "damage_class"], [(1, "status"), (2, "physical"), (3, "special")])
    _csv(m, "move_raw.csv", ["move_id", "move_name", "type_id", "damage_class_id", "accuracy", "pp", "power", "priority", "effect"],
         [(53, "flamethrower", 10, 3, 100.0, 15, 90.0, 0, "x"), (14, "swords-dance", 1, 1, None, 20, None, 0, "x"),
          (85, "thunderbolt", 13, 3, 100.0, 15, 90.0, 0, "x"), (247, "shadow-ball", 8, 3, 100.0, 15, 80.0, 0, "x"),
          (68, "counter", 2, 2, 100.0, 20, None, -5, "x"), (394, "flare-blitz", 10, 2, 100.0, 15, 120.0, 0, "x")])
    _csv(m, "pokemon_moves.csv", MOVE_COLUMNS,
         [(6, 53, 1, 1), (6, 53, 4, 0), (6, 14, 4, 0), (6, 68, 4, 0), (25, 85, 1, 1), (898, 247, 4, 0)])
    _csv(m, "pokemon_moves_champions.csv", MOVE_COLUMNS, [(6, 53, 12, 0), (6, 394, 12, 0), (25, 85, 12, 0)])
    _csv(m, "pokemon_nature_info.csv", ["nature_id", "nature_name", "decreased_stat", "increased_stat"],
         [(1, "hardy", None, None), (4, "adamant", 4.0, 2.0), (16, "modest", 2.0, 4.0)])
    _csv(m, "item_raw.csv", ["item_id", "item_name", "category", "effect"],
         [(1, "master-ball", "standard-balls", "x"), (211, "leftovers", "held-items", "x"), (264, "choice-scarf", "choice", "x"),
          (135, "sitrus-berry", "medicine", "x"), (17, "potion", "healing", "x"), (190, "pecha-berry-x", "unused", "x"),
          (2000, "hondew-berry", "baking-only", "x"), (2001, "charizardite-x", "mega-stones", "x"),
          (2002, "choice-scarf", "choice", "x")])   # duplicate name in the crawl: kept once
    return m


def _form(species, form, poke_id, types, stats):
    return {"species": species, "form": form, "poke_id": poke_id, "type_1": types[0],
            "type_2": types[1] if len(types) > 1 else None, **dict(zip(["hp", "atk", "def", "spatk", "spdef", "spe"], stats))}


FORMS = [_form("Charizard", "charizard", 6, ["fire", "flying"], [78, 84, 78, 109, 85, 100]),
         _form("Calyrex", "calyrex-shadow", 10194, ["psychic", "ghost"], [100, 85, 80, 165, 100, 150])]
MEGA_X = _form("Charizard", "charizard-mega-x", 10034, ["fire", "dragon"], [78, 130, 111, 130, 85, 100])
REGS = [{"id": "gen9vgc2025regi", "label": "Reg I 2025", "poke_ids": [6, 10194]},
        {"id": "gen9championsvgc2026regm-a", "label": "Champions Reg M-A 2026", "poke_ids": [6, 10034]}]


def _get(out, pid):
    return next(f for f in out["forms"] if f["poke_id"] == pid)


def test_only_forms_of_the_species_dimension_are_exported(master):
    out = build(master, FORMS, REGS)
    assert [f["poke_id"] for f in out["forms"]] == [10194, 6]                        # by species, then form
    assert {m["name"] for m in out["moves"]} == {"flamethrower", "flare-blitz", "shadow-ball"}   # thunderbolt: Pikachu only
    assert "static" not in json.dumps(out)


def test_a_form_has_a_learnset_per_game_of_the_exported_regulations(master):
    charizard = _get(build(master, FORMS, REGS), 6)
    assert charizard["learnsets"] == {SV: {"moves": [53], "version_group": SV, "poke_id": 6},
                                      CH: {"moves": [53, 394], "version_group": CH, "poke_id": 6}}


def test_only_the_games_of_the_exported_regulations_get_a_learnset(master):
    charizard = _get(build(master, FORMS, REGS[:1]), 6)
    assert list(charizard["learnsets"]) == [SV]


def test_a_form_keeps_its_own_typing_stats_and_abilities(master):
    charizard = _get(build(master, FORMS, REGS), 6)
    assert {k: v for k, v in charizard.items() if k != "learnsets"} == {
        "poke_id": 6, "species": "Charizard", "form": "charizard", "types": ["fire", "flying"],
        "base_stats": {"hp": 78, "atk": 84, "def": 78, "spatk": 109, "spdef": 85, "spe": 100},
        "abilities": ["blaze", "solar-power"], "abilities_from": None}


def test_regulations_are_listed_newest_first_with_their_game_and_exported_forms(master):
    out = build(master, FORMS + [MEGA_X], REGS + [{"id": "gen9vgc2026regf", "label": "Reg F 2026", "poke_ids": [6, 25]}])
    assert out["regulations"] == [
        {"id": "gen9championsvgc2026regm-a", "label": "Champions Reg M-A 2026", "version_group": CH, "forms": [6, 10034]},
        {"id": "gen9vgc2026regf", "label": "Reg F 2026", "version_group": SV, "forms": [6]},    # Pikachu: not exported
        {"id": "gen9vgc2025regi", "label": "Reg I 2025", "version_group": SV, "forms": [6, 10194]}]


def test_an_unmapped_regulation_fails_the_export(master):
    with pytest.raises(UnmappedRegulationError):
        build(master, FORMS, REGS + [{"id": "gen10vgc2027rega", "label": "Reg A 2027", "poke_ids": [6]}])


def test_a_game_without_its_crawled_learnsets_fails_the_export(master):
    (master / "pokemon_moves_champions.csv").unlink()
    with pytest.raises(CalcMasterError, match="pokemon_moves_champions.csv"):
        build(master, FORMS, REGS)


def test_an_alternate_form_without_rows_borrows_the_default_form_of_the_same_game_first(master):
    """A Mega form with its own Champions learnset but no Scarlet / Violet one (as in PokéAPI, #37)."""
    _add(master, "pokemon_moves_champions.csv", [(10034, 394, 12, 0)])
    _add(master, "pokemon_ability.csv", [(10034, 94, False)])
    mega = _get(build(master, FORMS + [MEGA_X], REGS), 10034)
    assert mega["learnsets"] == {SV: {"moves": [53], "version_group": SV, "poke_id": 6},
                                 CH: {"moves": [394], "version_group": CH, "poke_id": 10034}}
    assert mega["abilities"] == ["solar-power"] and mega["abilities_from"] is None


def test_a_game_without_data_for_the_form_or_its_default_falls_back_to_another_game_and_says_so(master):
    shadow = _get(build(master, FORMS, REGS), 10194)
    assert shadow["learnsets"][CH] == {"moves": [247], "version_group": SV, "poke_id": 898}   # fallback: SV, Calyrex
    assert shadow["learnsets"][SV] == {"moves": [247], "version_group": SV, "poke_id": 898}
    assert shadow["abilities"] == ["unnerve"] and shadow["abilities_from"] == 898
    assert shadow["types"] == ["psychic", "ghost"] and shadow["base_stats"]["spatk"] == 165   # never borrowed


def test_a_form_with_no_learnset_in_any_game_has_none_and_no_source(master):
    pd.read_csv(master / "pokemon_moves.csv").query("pokemon_id != 898").to_csv(master / "pokemon_moves.csv", index=False)
    shadow = _get(build(master, FORMS, REGS), 10194)
    assert shadow["learnsets"][SV] == {"moves": [], "version_group": None, "poke_id": None}


def test_a_form_with_its_own_learnset_and_abilities_borrows_nothing(master):
    _add(master, "pokemon_moves.csv", [(10194, 247, 1, 1)])
    _add(master, "pokemon_ability.csv", [(10194, 266, False)])
    shadow = _get(build(master, FORMS, REGS[:1]), 10194)
    assert shadow["learnsets"][SV] == {"moves": [247], "version_group": SV, "poke_id": 10194}
    assert shadow["abilities"] == ["as-one-spectrier"] and shadow["abilities_from"] is None


def test_a_form_whose_learnset_has_only_status_moves_keeps_it_and_borrows_nothing(master):
    """Borrow only where PokéAPI has no learnset rows at all, not where the rows hold no damaging move."""
    _add(master, "pokemon_moves.csv", [(10194, 14, 4, 0)])
    shadow = _get(build(master, FORMS, REGS[:1]), 10194)
    assert shadow["learnsets"][SV] == {"moves": [], "version_group": SV, "poke_id": 10194}


def test_status_and_powerless_moves_are_left_out(master):
    names = {m["name"] for m in build(master, FORMS, REGS)["moves"]}
    assert not names & {"swords-dance", "counter"}


def test_moves_natures_and_type_chart_use_names_not_ids(master):
    out = build(master, FORMS, REGS)
    assert {"id": 53, "name": "flamethrower", "type": "fire", "power": 90, "damage_class": "special"} in out["moves"]
    assert {"name": "adamant", "increased": "atk", "decreased": "spatk"} in out["natures"]
    assert {"name": "hardy", "increased": None, "decreased": None} in out["natures"]
    assert sorted(out["type_chart"]) == [["fire", "fire", 0.5], ["ghost", "ghost", 2.0], ["normal", "ghost", 0.0]]


def test_items_are_the_holdable_battle_items_by_name(master):
    """Team builder (#17): held items, choice items, mega stones and berries; not balls, medicine or baking berries."""
    assert build(master, FORMS, REGS)["items"] == [
        {"name": "charizardite-x", "category": "mega-stones"}, {"name": "choice-scarf", "category": "choice"},
        {"name": "leftovers", "category": "held-items"}, {"name": "sitrus-berry", "category": "berries"}]


def test_a_form_without_base_stats_or_typing_cannot_be_calculated_and_is_left_out(master):
    broken = _form("Arceus", "arceus", 493, [None], [None] * 6)
    out = build(master, FORMS + [broken], [{**REGS[0], "poke_ids": [6, 493]}])
    assert 493 not in {f["poke_id"] for f in out["forms"]} and out["regulations"][0]["forms"] == [6]
    assert out["skipped"] == ["arceus"]


def test_a_forbidden_column_in_the_master_data_fails(master):
    pd.read_csv(master / "move_raw.csv").assign(username="x").to_csv(master / "move_raw.csv", index=False)
    with pytest.raises(CalcMasterError):
        build(master, FORMS, REGS)


def test_cli_reads_species_forms_and_the_regulations_of_the_web_export(master, tmp_path):
    data, out = tmp_path / "data", tmp_path / "web" / "calc_master.json"
    (data / "team_usage").mkdir(parents=True)
    (data / "species_forms.json").write_text(json.dumps(FORMS), encoding="utf-8")
    (data / "manifest.json").write_text(json.dumps({"regulations": [{"id": r["id"], "label": r["label"]} for r in REGS]}),
                                        encoding="utf-8")
    for r in REGS:
        (data / "team_usage" / f"{r['id']}__all.json").write_text(
            json.dumps({"rows": [{"poke_id": p, "n": 500} for p in r["poke_ids"]]}), encoding="utf-8")
    assert main(["--master", str(master), "--data", str(data), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == build(master, FORMS, REGS)


def test_species_level_rows_of_the_team_usage_add_no_form(master, tmp_path):
    """#24: a masked / unlisted species row has poke_id null: no form is guessed for it (BR-05)."""
    data = tmp_path / "data"
    (data / "team_usage").mkdir(parents=True)
    (data / "manifest.json").write_text(json.dumps({"regulations": [{"id": "gen9vgc2025regi", "label": "Reg I 2025"}]}),
                                        encoding="utf-8")
    (data / "team_usage" / "gen9vgc2025regi__all.json").write_text(json.dumps({"rows": [
        {"poke_id": 6, "form_basis": "listed"}, {"poke_id": None, "form_basis": "unobserved"}]}), encoding="utf-8")
    assert read_regulations(data) == [{"id": "gen9vgc2025regi", "label": "Reg I 2025", "poke_ids": [6]}]
