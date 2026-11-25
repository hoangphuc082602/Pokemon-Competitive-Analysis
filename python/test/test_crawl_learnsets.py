"""#36: PokéAPI learnset / ability crawl (python.crawl_data.data_poke_move, data_poke_abi, pokeapi_crawl).
Recorded /pokemon payloads and fake fetches: no network, no MySQL."""
import importlib
import sys

import pandas as pd
import pytest
import requests

from python.crawl_data.data_poke_abi import extract_abilities
from python.crawl_data.data_poke_move import COLUMNS as MOVE_COLUMNS, extract_moves
from python.crawl_data.pokeapi_crawl import crawl_rows, fetch_json


def _ref(kind, name, rid):
    return {"name": name, "url": f"https://pokeapi.co/api/v2/{kind}/{rid}/"}


def _detail(group, method, method_id, level):
    return {"version_group": _ref("version-group", group, 0), "move_learn_method": _ref("move-learn-method", method, method_id),
            "level_learned_at": level}


# Trimmed recording of /pokemon/10191 (urshifu-rapid-strike): an alternate form with its own learnset.
URSHIFU_RS = {
    "id": 10191, "name": "urshifu-rapid-strike",
    "abilities": [{"ability": _ref("ability", "unseen-fist", 260), "is_hidden": False, "slot": 1}],
    "moves": [
        {"move": _ref("move", "surging-strikes", 818),
         "version_group_details": [_detail("sword-shield", "level-up", 1, 1), _detail("scarlet-violet", "level-up", 1, 1)]},
        {"move": _ref("move", "close-combat", 370),
         "version_group_details": [_detail("scarlet-violet", "level-up", 1, 52), _detail("scarlet-violet", "machine", 4, 0)]},
        {"move": _ref("move", "focus-punch", 264),                      # not learnable in Scarlet / Violet
         "version_group_details": [_detail("sword-shield", "machine", 4, 0)]},
    ],
}


def test_moves_keep_only_the_scarlet_violet_version_group_and_the_form_id():
    rows = extract_moves(URSHIFU_RS)
    assert sorted((r["pokemon_id"], r["move_id"], r["learn_method"], r["level_learned"]) for r in rows) == [
        (10191, 370, 1, 52), (10191, 370, 4, 0), (10191, 818, 1, 1)]


def test_a_form_without_scarlet_violet_moves_has_no_rows_but_is_not_an_error():
    mega = {"id": 10034, "name": "charizard-mega-x", "moves": [
        {"move": _ref("move", "flamethrower", 53), "version_group_details": [_detail("x-y", "machine", 4, 0)]}]}
    assert extract_moves(mega) == []


def test_a_payload_without_a_moves_list_is_an_error():
    with pytest.raises(KeyError):
        extract_moves({"id": 7, "name": "broken"})


def test_abilities_keep_the_form_id_and_the_hidden_flag():
    mega = {"id": 10034, "name": "charizard-mega-x",
            "abilities": [{"ability": _ref("ability", "tough-claws", 181), "is_hidden": False, "slot": 1}]}
    assert extract_abilities(mega) == [{"pokemon_id": 10034, "abi_id": 181, "hidden_abi": False}]
    assert [r["abi_id"] for r in extract_abilities(URSHIFU_RS)] == [260]


def test_a_form_without_abilities_in_pokeapi_has_no_rows_but_is_not_an_error():
    """PokéAPI has no abilities yet for some new forms (e.g. /pokemon/10301 zygarde-mega): a real absence."""
    assert extract_abilities({"id": 10301, "name": "zygarde-mega", "abilities": []}) == []


def test_a_payload_without_an_abilities_list_is_an_error():
    with pytest.raises(KeyError):
        extract_abilities({"id": 7, "name": "broken"})


MEGA_X = {"id": 10034, "name": "charizard-mega-x", "moves": [
    {"move": _ref("move", "flamethrower", 53), "version_group_details": [_detail("x-y", "machine", 4, 0)]}]}


def _fetch(api, calls):
    def fetch(pid):
        calls.append(pid)
        if pid not in api:
            raise requests.HTTPError(f"404 Client Error for pokemon {pid}")
        return api[pid]
    return fetch


def _crawl(tmp_path, ids, api, calls):
    return crawl_rows(ids, _fetch(api, calls), extract_moves, MOVE_COLUMNS, tmp_path / "pokemon_moves.csv",
                      tmp_path / "pokemon_moves_failures.csv", tmp_path / "pokemon_moves_progress.csv", delay=0)


def test_crawl_writes_rows_records_empty_learnsets_and_logs_failures(tmp_path):
    counts = _crawl(tmp_path, [10191, 10034, 99999], {10191: URSHIFU_RS, 10034: MEGA_X}, [])
    assert pd.read_csv(tmp_path / "pokemon_moves.csv")["pokemon_id"].tolist() == [10191, 10191, 10191]
    progress = pd.read_csv(tmp_path / "pokemon_moves_progress.csv")
    assert dict(zip(progress["pokemon_id"], progress["rows"])) == {10191: 3, 10034: 0}   # 0 rows = crawled, none in SV
    failed = pd.read_csv(tmp_path / "pokemon_moves_failures.csv")
    assert failed["pokemon_id"].tolist() == [99999] and "404" in failed["error"].iloc[0]
    assert counts == {"already_done": 0, "crawled": 2, "empty": 1, "failed": 1}


def test_a_rerun_skips_crawled_ids_even_without_rows_and_retries_failures(tmp_path):
    api = {10191: URSHIFU_RS, 10034: MEGA_X}
    _crawl(tmp_path, [10191, 10034, 25], api, [])
    calls = []
    counts = _crawl(tmp_path, [10191, 10034, 25], {**api, 25: {"id": 25, "name": "pikachu", "moves": []}}, calls)
    assert calls == [25]                                                    # 10034 had no rows but was crawled
    assert len(pd.read_csv(tmp_path / "pokemon_moves.csv")) == 3            # nothing written twice
    assert pd.read_csv(tmp_path / "pokemon_moves_failures.csv").empty       # this run's failures only
    assert counts == {"already_done": 2, "crawled": 1, "empty": 1, "failed": 0}


def test_ids_already_in_an_output_written_before_the_progress_file_count_as_done(tmp_path):
    pd.DataFrame([(10191, 818, 1, 1)], columns=MOVE_COLUMNS).to_csv(tmp_path / "pokemon_moves.csv", index=False)
    calls = []
    _crawl(tmp_path, [10191, 10034], {10191: URSHIFU_RS, 10034: MEGA_X}, calls)
    assert calls == [10034]


class _Response:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


class _Session:
    """Replays a script of responses / exceptions; records the urls asked."""
    def __init__(self, *script):
        self.script, self.urls = list(script), []

    def get(self, url, timeout):
        self.urls.append(url)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def test_fetch_retries_rate_limits_server_errors_and_timeouts_with_growing_backoff():
    session = _Session(_Response(429), requests.Timeout("slow"), _Response(503), _Response(200, {"id": 1}))
    sleeps = []
    assert fetch_json(session, "u", retries=3, backoff=1.0, sleep=sleeps.append) == {"id": 1}
    assert session.urls == ["u"] * 4
    assert sleeps == [1.0, 2.0, 4.0]


def test_fetch_does_not_retry_a_not_found():
    session, sleeps = _Session(_Response(404)), []
    with pytest.raises(requests.HTTPError, match="404"):
        fetch_json(session, "u", retries=3, backoff=1.0, sleep=sleeps.append)
    assert len(session.urls) == 1 and sleeps == []


def test_fetch_gives_up_after_the_last_retry_with_the_last_error():
    session, sleeps = _Session(_Response(500), _Response(502)), []
    with pytest.raises(requests.HTTPError, match="502"):
        fetch_json(session, "u", retries=1, backoff=0.5, sleep=sleeps.append)
    assert sleeps == [0.5]


def test_importing_the_crawl_modules_fetches_and_writes_nothing(monkeypatch, tmp_path):
    def no_network(*a, **k):
        raise AssertionError("network used on import")
    monkeypatch.setattr(requests.Session, "request", no_network)
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("python.database.db_connection", None)
    for name in ("python.crawl_data.data_poke_move", "python.crawl_data.data_poke_abi"):
        importlib.reload(importlib.import_module(name))
    assert list(tmp_path.iterdir()) == []
    assert "python.database.db_connection" not in sys.modules                 # MySQL only with --to-mysql


def test_main_crawls_the_given_ids_into_the_csvs(monkeypatch, tmp_path):
    from python.crawl_data import data_poke_abi, data_poke_move
    api = {"https://pokeapi.co/api/v2/pokemon/10191/": URSHIFU_RS}
    monkeypatch.setattr(requests.Session, "get",
                        lambda self, url, timeout: _Response(200, api[url]) if url in api else _Response(404))
    for module, out in ((data_poke_move, "m.csv"), (data_poke_abi, "a.csv")):
        assert module.main(["--ids", "10191", "404", "--out", str(tmp_path / out), "--delay", "0"]) == 0
        assert pd.read_csv(tmp_path / out)["pokemon_id"].unique().tolist() == [10191]
        assert pd.read_csv(tmp_path / out.replace(".csv", "_failures.csv"))["pokemon_id"].tolist() == [404]
        assert (tmp_path / out.replace(".csv", "_progress.csv")).exists()
