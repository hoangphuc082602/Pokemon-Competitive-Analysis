"""Seam 2: PokéAPI type crawler (python.crawl_data.data_pokemon) with a fake fetch: no network."""
import pandas as pd
import requests

from python.crawl_data.data_pokemon import crawl_types


def _pokemon(pid, *types):
    return {"id": pid, "name": f"p{pid}",
            "types": [{"slot": slot, "type": {"name": t, "url": f"https://pokeapi.co/api/v2/type/{tid}/"}}
                      for slot, (t, tid) in reversed(list(enumerate(types, start=1)))]}   # API order is not trusted


API = {892: _pokemon(892, ("fighting", 2), ("dark", 17)),
       10191: _pokemon(10191, ("fighting", 2), ("water", 11)),          # alternate form: id >= 10001
       25: _pokemon(25, ("electric", 13))}


def _fetch(calls):
    def fetch(pid):
        calls.append(pid)
        if pid not in API:
            raise requests.HTTPError(f"404 Client Error for pokemon {pid}")
        return API[pid]
    return fetch


def test_crawls_base_and_alternate_forms_and_logs_failures(tmp_path):
    out, failed = tmp_path / "pokemon_type_raw.csv", tmp_path / "pokemon_type_failures.csv"
    calls = []
    counts = crawl_types([892, 10191, 25, 99999], _fetch(calls), out, failed, delay=0)
    rows = pd.read_csv(out).sort_values(["pokemon_id", "slot"]).values.tolist()
    assert rows == [[25, 13, 1], [892, 2, 1], [892, 17, 2], [10191, 2, 1], [10191, 11, 2]]
    assert pd.read_csv(failed)[["pokemon_id"]].values.ravel().tolist() == [99999]
    assert "404" in pd.read_csv(failed)["error"].iloc[0]
    assert counts == {"already_done": 0, "base_forms": 2, "alternate_forms": 1, "failed": 1}


def test_a_rerun_resumes_skipping_ids_already_in_the_output_and_retries_failures(tmp_path):
    out, failed = tmp_path / "pokemon_type_raw.csv", tmp_path / "pokemon_type_failures.csv"
    crawl_types([892, 99999], _fetch([]), out, failed, delay=0)
    API[99999] = _pokemon(99999, ("normal", 1))
    try:
        calls = []
        counts = crawl_types([892, 10191, 99999], _fetch(calls), out, failed, delay=0)
    finally:
        del API[99999]
    assert calls == [10191, 99999]                                      # 892 was already crawled
    assert sorted(pd.read_csv(out)["pokemon_id"].unique().tolist()) == [892, 10191, 99999]
    assert len(pd.read_csv(out)) == 5                                   # nothing written twice
    assert pd.read_csv(failed).empty                                    # failures file = this run's failures
    assert counts == {"already_done": 1, "base_forms": 0, "alternate_forms": 2, "failed": 0}


def test_a_response_without_types_is_a_failure_not_an_empty_row(tmp_path):
    out, failed = tmp_path / "t.csv", tmp_path / "f.csv"
    API[7] = {"id": 7, "name": "broken"}
    try:
        counts = crawl_types([7], _fetch([]), out, failed, delay=0)
    finally:
        del API[7]
    assert counts["failed"] == 1 and pd.read_csv(failed)["pokemon_id"].tolist() == [7]
    assert pd.read_csv(out).empty


def test_a_pokemon_with_an_empty_type_list_is_a_failure(tmp_path):
    API[8] = {"id": 8, "name": "x", "types": []}
    try:
        counts = crawl_types([8], _fetch([]), tmp_path / "t.csv", tmp_path / "f.csv", delay=0)
    finally:
        del API[8]
    assert counts["failed"] == 1


class _Response:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


def test_main_retries_rate_limits_server_errors_and_timeouts_and_logs_a_not_found(monkeypatch, tmp_path):
    from python.crawl_data import data_pokemon, pokeapi_crawl
    script = {"https://pokeapi.co/api/v2/pokemon/892/":
              [_Response(429), requests.Timeout("slow"), _Response(503), _Response(200, API[892])],
              "https://pokeapi.co/api/v2/pokemon/404/": [_Response(404)]}

    def get(self, url, timeout):
        step = script[url].pop(0)
        if isinstance(step, Exception):
            raise step
        return step
    sleeps = []
    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr(pokeapi_crawl.time, "sleep", sleeps.append)
    out, failed = tmp_path / "pokemon_type_raw.csv", tmp_path / "pokemon_type_failures.csv"
    assert data_pokemon.main(["--ids", "892", "404", "--out", str(out), "--failures", str(failed),
                              "--delay", "0"]) == 0
    assert pd.read_csv(out).values.tolist() == [[892, 2, 1], [892, 17, 2]]
    assert pd.read_csv(failed)["pokemon_id"].tolist() == [404]
    assert sleeps == [1.0, 2.0, 4.0]                                    # backoff of the 3 transient errors
    assert script["https://pokeapi.co/api/v2/pokemon/892/"] == []
