from collections import Counter

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from python.data_quality.pokemon_name_mapping import (
    build_mapping,
    count_names_from_parquet,
    coverage,
    load_master_names,
    load_overrides,
    normalize_name,
    write_mapping_table,
)


@pytest.fixture
def master():
    return pd.DataFrame(
        [
            (1, "flutter-mane"),
            (2, "urshifu-rapid-strike"),
            (3, "mimikyu-disguised"),
            (4, "indeedee-female"),
            (5, "mr-mime"),
        ],
        columns=["poke_id", "pokemon"],
    )


# ---------- normalize_name ----------
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Flutter Mane", "flutter-mane"),
        ("Urshifu-Rapid-Strike", "urshifu-rapid-strike"),
        ("Mr. Mime", "mr-mime"),
        ("Type: Null", "type-null"),
        ("Farfetch’d", "farfetchd"),
        ("Flabébé", "flabebe"),
        ("  Ho-Oh ", "ho-oh"),
        ("Porygon-Z", "porygon-z"),
        ("flutter_mane", "flutter-mane"),
        ("Iron  Hands", "iron-hands"),
    ],
)
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


# ---------- build_mapping ----------
def test_exact_match_after_normalisation(master):
    mapping, unmatched = build_mapping(Counter({"Flutter Mane": 10, "Urshifu-Rapid-Strike": 5}), master)
    assert unmatched.empty
    row = mapping.set_index("showdown_name").loc["Flutter Mane"]
    assert (row.poke_id, row.pokemon, row.method, row.n_rows) == (1, "flutter-mane", "exact", 10)


def test_override_wins_and_is_marked(master):
    mapping, unmatched = build_mapping(Counter({"Indeedee-F": 3}), master, {"Indeedee-F": "indeedee-female"})
    assert unmatched.empty
    assert mapping.iloc[0].to_dict() == {
        "showdown_name": "Indeedee-F", "poke_id": 4, "pokemon": "indeedee-female", "method": "override", "n_rows": 3,
    }


def test_unmatched_is_reported_with_suggestions_but_never_auto_applied(master):
    # Base-form name: a prefix suggestion exists, but it must NOT be mapped silently.
    mapping, unmatched = build_mapping(Counter({"Mimikyu": 7, "Flutter Mane": 1}), master)
    assert list(mapping.showdown_name) == ["Flutter Mane"]
    assert list(unmatched.showdown_name) == ["Mimikyu"]
    assert "mimikyu-disguised" in unmatched.iloc[0].suggestions


def test_unmatched_sorted_by_frequency(master):
    _, unmatched = build_mapping(Counter({"Foo": 2, "Bar": 90, "Baz": 10}), master)
    assert list(unmatched.showdown_name) == ["Bar", "Baz", "Foo"]


def test_override_to_unknown_pokemon_fails_loudly(master):
    with pytest.raises(ValueError, match="not in the master data"):
        build_mapping(Counter({"X": 1}), master, {"X": "no-such-pokemon"})


def test_ambiguous_master_fails_loudly():
    dup = pd.DataFrame([(1, "Mr. Mime"), (2, "mr-mime")], columns=["poke_id", "pokemon"])
    with pytest.raises(ValueError, match="ambiguous"):
        build_mapping(Counter({"Mr. Mime": 1}), dup)


# ---------- coverage (row-weighted, not just distinct names) ----------
def test_coverage_is_weighted_by_rows(master):
    mapping, unmatched = build_mapping(Counter({"Flutter Mane": 99, "Mimikyu": 1}), master)
    assert coverage(mapping, unmatched) == {
        "rows_total": 100, "rows_matched_pct": 99.0, "names_total": 2, "names_matched_pct": 50.0,
    }


# ---------- inputs / outputs ----------
def test_load_overrides(tmp_path):
    f = tmp_path / "o.csv"
    f.write_text("showdown_name,pokemon\nIndeedee-F,Indeedee Female\n", encoding="utf-8")
    assert load_overrides(f) == {"Indeedee-F": "indeedee-female"}


def test_load_overrides_header_only(tmp_path):
    f = tmp_path / "o.csv"
    f.write_text("showdown_name,pokemon\n", encoding="utf-8")
    assert load_overrides(f) == {}


def test_count_names_streams_in_batches(tmp_path):
    path = tmp_path / "slots.parquet"
    pd.DataFrame({"pokemon_name": ["A", "B", "A", None, "A", "B"], "slot_no": range(6)}).to_parquet(path)
    assert count_names_from_parquet(path, batch_size=2) == Counter({"A": 3, "B": 2})


def test_master_and_mapping_table_roundtrip_sqlite(master):
    engine = create_engine("sqlite://")
    master.assign(species_id=0).to_sql("pokemon_stats", engine, index=False)
    loaded = load_master_names(engine)
    assert list(loaded.pokemon) == list(master.pokemon)

    mapping, _ = build_mapping(Counter({"Flutter Mane": 5}), loaded)
    write_mapping_table(mapping, engine)
    write_mapping_table(mapping, engine)  # idempotent: replace, not append
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT showdown_name, poke_id, method FROM showdown_pokemon_map")).fetchall()
    assert rows == [("Flutter Mane", 1, "exact")]


def test_no_suggestions_for_unrelated_name(master):
    _, unmatched = build_mapping(Counter({"Zzzzzzzz": 1}), master)
    assert unmatched.iloc[0].suggestions == ""


# ---------- the committed overrides file ----------
def test_committed_overrides_are_well_formed():
    from python.data_quality.pokemon_name_mapping import DEFAULT_OVERRIDES

    df = pd.read_csv(DEFAULT_OVERRIDES, dtype=str)
    assert list(df.columns) == ["showdown_name", "pokemon"]
    assert not df.duplicated("showdown_name").any(), "duplicate Showdown names in overrides"
    assert not df.isna().any().any()
    # Masked names ("Urshifu-*") cannot be resolved by name: mapping them to one forme would be wrong
    # for the other forme. They are fixed at parser level instead.
    assert not df.showdown_name.str.contains(r"\*").any()
    assert (df.pokemon == df.pokemon.map(normalize_name)).all(), "override targets must already be slugs"