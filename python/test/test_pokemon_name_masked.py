from collections import Counter

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from python.data_quality.pokemon_name_mapping import build_mapping, coverage, write_mapping_table


@pytest.fixture
def master():
    rows = [
        (892, "urshifu-single-strike", 892), (10248, "urshifu-rapid-strike", 892),
        (888, "zacian", 888), (10188, "zacian-crowned", 888),
        (982, "dudunsparce-two-segment", 982), (10256, "dudunsparce-three-segment", 982),
        (25, "pikachu", 25),
        (100, "porygon", 137), (233, "porygon2", 233),     # different species sharing a prefix
        (9000, "foo-a", 9000), (9001, "foo-b", 9001),      # same family prefix, two species ids
    ]
    return pd.DataFrame(rows, columns=["poke_id", "pokemon", "species_id"])


def _row(mapping, name):
    return mapping[mapping["showdown_name"] == name].iloc[0]


def test_masked_name_maps_to_species_only(master):
    mapping, unmatched = build_mapping(Counter({"Urshifu-*": 10}), master)
    r = _row(mapping, "Urshifu-*")
    assert unmatched.empty
    assert pd.isna(r["poke_id"]) and pd.isna(r["pokemon"])
    assert r["species_id"] == 892
    assert (r["method"], r["form_status"]) == ("masked", "masked")


def test_family_with_two_forms_of_one_species_is_accepted(master):
    mapping, _ = build_mapping(Counter({"Dudunsparce-*": 1, "Zacian-*": 1}), master)
    assert _row(mapping, "Dudunsparce-*")["species_id"] == 982
    assert _row(mapping, "Zacian-*")["species_id"] == 888


def test_known_name_keeps_its_form_and_gets_species_id(master):
    mapping, _ = build_mapping(Counter({"Pikachu": 5}), master)
    r = _row(mapping, "Pikachu")
    assert (r["poke_id"], r["species_id"], r["form_status"]) == (25, 25, "known")


def test_masked_name_spanning_two_species_stays_unmatched(master):
    mapping, unmatched = build_mapping(Counter({"Foo-*": 3}), master)
    assert mapping.empty
    assert list(unmatched["showdown_name"]) == ["Foo-*"]


def test_masked_prefix_does_not_leak_into_other_species(master):
    mapping, _ = build_mapping(Counter({"Porygon-*": 1}), master)
    assert _row(mapping, "Porygon-*")["species_id"] == 137


def test_unknown_masked_species_stays_unmatched(master):
    mapping, unmatched = build_mapping(Counter({"Missingno-*": 2}), master)
    assert mapping.empty and list(unmatched["showdown_name"]) == ["Missingno-*"]


def test_explicit_override_wins_over_masked_rule(master):
    mapping, _ = build_mapping(Counter({"Urshifu-*": 1}), master, {"Urshifu-*": "urshifu-rapid-strike"})
    r = _row(mapping, "Urshifu-*")
    assert (r["method"], r["form_status"], r["poke_id"]) == ("override", "known", 10248)


def test_without_species_column_masked_names_stay_unmatched(master):
    mapping, unmatched = build_mapping(Counter({"Urshifu-*": 1}), master.drop(columns="species_id"))
    assert mapping.empty and list(unmatched["showdown_name"]) == ["Urshifu-*"]


def test_coverage_separates_form_level_from_species_only(master):
    mapping, unmatched = build_mapping(Counter({"Pikachu": 90, "Urshifu-*": 8, "Missingno": 2}), master)
    cov = coverage(mapping, unmatched)
    assert cov["rows_total"] == 100
    assert cov["rows_matched_pct"] == 90.0
    assert cov["rows_species_only_pct"] == 8.0
    assert (cov["names_total"], cov["names_species_only"]) == (3, 1)


def test_write_mapping_table_keeps_null_poke_id_for_masked(master):
    mapping, _ = build_mapping(Counter({"Pikachu": 1, "Urshifu-*": 1}), master)
    engine = create_engine("sqlite://")
    write_mapping_table(mapping, engine)
    with engine.connect() as con:
        rows = con.execute(text(
            "SELECT showdown_name, poke_id, species_id, form_status FROM showdown_pokemon_map ORDER BY showdown_name"
        )).all()
    assert rows == [("Pikachu", 25, 25, "known"), ("Urshifu-*", None, 892, "masked")]