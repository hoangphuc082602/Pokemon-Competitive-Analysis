import pandas as pd
import pytest

from python.data_quality.backfill_masked_forms import explain, probe_events, resolve_masked, side_coverage


def _slots(rows):
    return pd.DataFrame(rows, columns=["battle_id", "player_side", "slot_no", "pokemon_name"])


def _players(rows):
    return pd.DataFrame(rows, columns=["battle_id", "side", "username"])


def _events(rows):
    return pd.DataFrame(rows, columns=["battle_id", "username", "pokemon_name"])


PLAYERS = _players([("b1", "p1", "alice"), ("b1", "p2", "bob")])


def _row(res, side, name):
    return res[(res["player_side"] == side) & (res["pokemon_name"] == name)].iloc[0]


def test_form_resolved_from_switch_event():
    slots = _slots([("b1", "p1", 1, "Urshifu-*")])
    res = resolve_masked(slots, PLAYERS, _events([("b1", "alice", "Urshifu-Rapid-Strike")]))
    assert res.iloc[0]["status"] == "resolved"
    assert res.iloc[0]["resolved_name"] == "Urshifu-Rapid-Strike"


def test_base_form_without_suffix_matches():
    slots = _slots([("b1", "p1", 1, "Zacian-*")])
    res = resolve_masked(slots, PLAYERS, _events([("b1", "alice", "Zacian")]))
    assert res.iloc[0]["resolved_name"] == "Zacian"


def test_sides_are_not_mixed_up():
    slots = _slots([("b1", "p1", 1, "Urshifu-*"), ("b1", "p2", 1, "Urshifu-*")])
    events = _events([("b1", "alice", "Urshifu-Rapid-Strike"), ("b1", "bob", "Urshifu")])
    res = resolve_masked(slots, PLAYERS, events)
    assert _row(res, "p1", "Urshifu-*")["resolved_name"] == "Urshifu-Rapid-Strike"
    assert _row(res, "p2", "Urshifu-*")["resolved_name"] == "Urshifu"


def test_unknown_when_form_never_seen():
    slots = _slots([("b1", "p1", 1, "Zamazenta-*")])
    res = resolve_masked(slots, PLAYERS, _events([("b1", "alice", "Incineroar")]))
    assert res.iloc[0]["status"] == "unknown"
    assert res.iloc[0]["resolved_name"] is None


def test_ambiguous_when_two_forms_seen():
    slots = _slots([("b1", "p1", 1, "Greninja-*")])
    events = _events([("b1", "alice", "Greninja"), ("b1", "alice", "Greninja-Ash")])
    res = resolve_masked(slots, PLAYERS, events)
    assert res.iloc[0]["status"] == "ambiguous"
    assert res.iloc[0]["n_candidates"] == 2
    assert res.iloc[0]["resolved_name"] is None


def test_other_species_with_same_first_letters_do_not_match():
    slots = _slots([("b1", "p1", 1, "Zacian-*")])
    res = resolve_masked(slots, PLAYERS, _events([("b1", "alice", "Zamazenta-Crowned")]))
    assert res.iloc[0]["status"] == "unknown"


def test_unmasked_slots_are_ignored():
    slots = _slots([("b1", "p1", 1, "Incineroar"), ("b1", "p1", 2, "Urshifu-*")])
    res = resolve_masked(slots, PLAYERS, _events([]))
    assert list(res["pokemon_name"]) == ["Urshifu-*"]


def test_no_player_status_when_side_missing():
    slots = _slots([("b9", "p1", 1, "Urshifu-*")])
    res = resolve_masked(slots, PLAYERS, _events([("b9", "alice", "Urshifu-Rapid-Strike")]))
    assert res.iloc[0]["status"] == "no_player"


def test_brought_n_counts_distinct_species_seen_for_the_player():
    slots = _slots([("b1", "p1", 1, "Zacian-*")])
    events = _events([("b1", "alice", n) for n in ["Incineroar", "Rillaboom", "Flutter Mane", "Urshifu-Rapid-Strike"]])
    res = resolve_masked(slots, PLAYERS, events)
    assert res.iloc[0]["brought_n"] == 4
    assert res.iloc[0]["status"] == "unknown"


def test_side_coverage():
    slots = _slots([("b1", "p1", 1, "A"), ("b1", "p2", 1, "B"), ("b2", "p1", 1, "C")])
    assert side_coverage(slots, PLAYERS) == 2 / 3
    assert side_coverage(slots, _players([("b1", "P1", "x")])) == 0.0


def test_probe_events_counts_matching_names_case_insensitively():
    ev = _events([("b1", "a", "Urshifu"), ("b1", "a", "Urshifu"), ("b1", "a", "urshifu-Rapid-Strike"), ("b1", "a", "Incineroar")])
    out = probe_events(ev, "URSHIFU")
    assert out["Urshifu"] == 2
    assert out["urshifu-Rapid-Strike"] == 1
    assert "Incineroar" not in out.index


def test_explain_prints_raw_rows(capsys):
    slots = _slots([("b1", "p1", 1, "Urshifu-*")])
    explain(slots, PLAYERS, _events([("b1", "alice ", "Urshifu")]), 1, "urshifu")
    out = capsys.readouterr().out
    assert "'alice '" in out and "'Urshifu-*'" in out


def test_read_filtered_converts_dictionary_columns(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from python.data_quality.backfill_masked_forms import read_filtered

    table = pa.table({"battle_id": pa.array(["b1", "b2"]).dictionary_encode(),
                      "pokemon_name": pa.array(["Urshifu", "Zacian"]).dictionary_encode()})
    path = tmp_path / "t.parquet"
    pq.write_table(table, path)
    df = read_filtered(path, ["battle_id", "pokemon_name"], lambda b: pa.array([True] * b.num_rows))
    assert df["pokemon_name"].dtype == object
    assert list(df["pokemon_name"]) == ["Urshifu", "Zacian"]


@pytest.mark.parametrize("dtype", ["object", "string", "string[pyarrow]", "category"])
def test_resolution_is_independent_of_pandas_string_dtype(dtype):
    def conv(df):
        return df.astype({c: dtype for c in df.columns if df[c].dtype == object})

    slots = _slots([("b1", "p1", 5, "Urshifu-*")])
    events = _events([("b1", "alice", "Urshifu"), ("b1", "alice", "Sylveon")])
    res = resolve_masked(conv(slots), conv(PLAYERS), conv(events))
    assert res.iloc[0]["status"] == "resolved"
    assert res.iloc[0]["resolved_name"] == "Urshifu"