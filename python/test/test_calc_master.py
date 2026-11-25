"""Damage-calc master data export (#16): only the forms of the species dimension (species_forms.json) and the
damaging moves of their learnsets. Seam: calc_master.build(master_dir, forms) -> dict."""
import json

import pandas as pd
import pytest

from python.analytics.calc_master import CalcMasterError, build, main


def _csv(master, name, columns, rows):
    pd.DataFrame(rows, columns=columns).to_csv(master / name, index=False)


@pytest.fixture
def master(tmp_path):
    """Synthetic PokéAPI CSVs in the crawl_data layout. Charizard (6) and Calyrex-Shadow (10194, form of 898) are in
    the species dimension; Pikachu (25) is not."""
    m = tmp_path / "raw"
    m.mkdir()
    _csv(m, "stats_raw.csv", ["poke_id", "pokemon", "species_id", "hp", "atk", "def", "spatk", "spdef", "spe"],
         [(6, "charizard", 6, 78, 84, 78, 109, 85, 100), (25, "pikachu", 25, 35, 55, 40, 50, 50, 90),
          (898, "calyrex", 898, 100, 80, 80, 80, 80, 80), (10194, "calyrex-shadow", 898, 100, 85, 80, 165, 100, 150)])
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
          (68, "counter", 2, 2, 100.0, 20, None, -5, "x")])
    _csv(m, "pokemon_moves.csv", ["pokemon_id", "move_id", "learn_method", "level_learned"],
         [(6, 53, 1, 1), (6, 53, 4, 0), (6, 14, 4, 0), (6, 68, 4, 0), (25, 85, 1, 1), (898, 247, 4, 0)])
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


def test_only_forms_of_the_species_dimension_are_exported(master):
    out = build(master, FORMS)
    assert [f["poke_id"] for f in out["forms"]] == [10194, 6]                        # by species, then form
    assert {m["name"] for m in out["moves"]} == {"flamethrower", "shadow-ball"}      # thunderbolt: Pikachu only
    assert "static" not in json.dumps(out)


def test_a_form_keeps_its_own_typing_stats_abilities_and_damaging_learnset(master):
    charizard = next(f for f in build(master, FORMS)["forms"] if f["poke_id"] == 6)
    assert charizard == {"poke_id": 6, "species": "Charizard", "form": "charizard", "types": ["fire", "flying"],
                         "base_stats": {"hp": 78, "atk": 84, "def": 78, "spatk": 109, "spdef": 85, "spe": 100},
                         "abilities": ["blaze", "solar-power"], "moves": [53], "borrowed_from": None}


def test_an_alternate_form_without_rows_borrows_the_default_form_and_says_so(master):
    shadow = next(f for f in build(master, FORMS)["forms"] if f["poke_id"] == 10194)
    assert shadow["abilities"] == ["unnerve"] and shadow["moves"] == [247]
    assert shadow["borrowed_from"] == 898
    assert shadow["types"] == ["psychic", "ghost"] and shadow["base_stats"]["spatk"] == 165   # never borrowed


def test_status_and_powerless_moves_are_left_out(master):
    names = {m["name"] for m in build(master, FORMS)["moves"]}
    assert not names & {"swords-dance", "counter"}


def test_moves_natures_and_type_chart_use_names_not_ids(master):
    out = build(master, FORMS)
    assert {"id": 53, "name": "flamethrower", "type": "fire", "power": 90, "damage_class": "special"} in out["moves"]
    assert {"name": "adamant", "increased": "atk", "decreased": "spatk"} in out["natures"]
    assert {"name": "hardy", "increased": None, "decreased": None} in out["natures"]
    assert sorted(out["type_chart"]) == [["fire", "fire", 0.5], ["ghost", "ghost", 2.0], ["normal", "ghost", 0.0]]


def test_items_are_the_holdable_battle_items_by_name(master):
    """Team builder (#17): held items, choice items, mega stones and berries; not balls, medicine or baking berries."""
    assert build(master, FORMS)["items"] == [
        {"name": "charizardite-x", "category": "mega-stones"}, {"name": "choice-scarf", "category": "choice"},
        {"name": "leftovers", "category": "held-items"}, {"name": "sitrus-berry", "category": "berries"}]


def test_a_form_without_base_stats_or_typing_cannot_be_calculated_and_is_left_out(master):
    broken = _form("Arceus", "arceus", 493, [None], [None] * 6)
    out = build(master, FORMS + [broken])
    assert 493 not in {f["poke_id"] for f in out["forms"]}
    assert out["skipped"] == ["arceus"]


def test_a_forbidden_column_in_the_master_data_fails(master):
    pd.read_csv(master / "move_raw.csv").assign(username="x").to_csv(master / "move_raw.csv", index=False)
    with pytest.raises(CalcMasterError):
        build(master, FORMS)


def test_cli_reads_species_forms_and_writes_json(master, tmp_path):
    forms, out = tmp_path / "species_forms.json", tmp_path / "web" / "calc_master.json"
    forms.write_text(json.dumps(FORMS), encoding="utf-8")
    assert main(["--master", str(master), "--forms", str(forms), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == build(master, FORMS)


def test_a_form_with_its_own_abilities_but_no_learnset_borrows_only_the_learnset(master):
    """#36: PokéAPI gives Mega forms their own ability but no Scarlet / Violet learnset: they share the default form's."""
    stats = pd.read_csv(master / "stats_raw.csv")
    pd.concat([stats, pd.DataFrame([(10034, "charizard-mega-x", 6, 78, 130, 111, 130, 85, 100)], columns=stats.columns)]
              ).to_csv(master / "stats_raw.csv", index=False)
    pa = pd.read_csv(master / "pokemon_ability.csv")
    pd.concat([pa, pd.DataFrame([(10034, 94, False)], columns=pa.columns)]).to_csv(master / "pokemon_ability.csv", index=False)
    mega = _form("Charizard", "charizard-mega-x", 10034, ["fire", "dragon"], [78, 130, 111, 130, 85, 100])
    out = next(f for f in build(master, FORMS + [mega])["forms"] if f["poke_id"] == 10034)
    assert out["abilities"] == ["solar-power"]          # its own, not blaze + solar-power
    assert out["moves"] == [53]                          # Charizard's damaging learnset
    assert out["borrowed_from"] == 6


def test_a_form_with_its_own_learnset_and_abilities_borrows_nothing(master):
    pm = pd.read_csv(master / "pokemon_moves.csv")
    pd.concat([pm, pd.DataFrame([(10194, 247, 1, 1)], columns=pm.columns)]).to_csv(master / "pokemon_moves.csv", index=False)
    pa = pd.read_csv(master / "pokemon_ability.csv")
    pd.concat([pa, pd.DataFrame([(10194, 266, False)], columns=pa.columns)]).to_csv(master / "pokemon_ability.csv", index=False)
    shadow = next(f for f in build(master, FORMS)["forms"] if f["poke_id"] == 10194)
    assert shadow["abilities"] == ["as-one-spectrier"] and shadow["moves"] == [247] and shadow["borrowed_from"] is None


def test_a_form_whose_learnset_has_only_status_moves_keeps_it_and_borrows_nothing(master):
    """Borrow only where PokéAPI has no learnset rows at all, not where the rows hold no damaging move."""
    pm = pd.read_csv(master / "pokemon_moves.csv")
    pd.concat([pm, pd.DataFrame([(10194, 14, 4, 0)], columns=pm.columns)]).to_csv(master / "pokemon_moves.csv", index=False)
    pa = pd.read_csv(master / "pokemon_ability.csv")
    pd.concat([pa, pd.DataFrame([(10194, 266, False)], columns=pa.columns)]).to_csv(master / "pokemon_ability.csv", index=False)
    shadow = next(f for f in build(master, FORMS)["forms"] if f["poke_id"] == 10194)
    assert shadow["moves"] == [] and shadow["borrowed_from"] is None
