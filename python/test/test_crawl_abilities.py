"""#44: PokéAPI ability crawl (python.crawl_data.data_ability). Recorded /ability payloads, fake fetches / sessions:
no network, no MySQL."""
import importlib
import sys

import pandas as pd
import pytest
import requests

from python.crawl_data.data_ability import extract_ability


def _entry(lang, short):
    return {"effect": f"long {short}", "short_effect": short,
            "language": {"name": lang, "url": f"https://pokeapi.co/api/v2/language/{lang}/"}}


# Trimmed recording of /ability/22.
INTIMIDATE = {"id": 22, "name": "intimidate", "is_main_series": True,
              "effect_entries": [_entry("de", "Senkt den Angriff."),
                                 _entry("en", "Lowers opponents' Attack by one stage upon entering battle.")]}


def test_an_ability_row_has_its_id_name_and_english_short_effect():
    assert extract_ability(INTIMIDATE) == [{"ability_id": 22, "ability_name": "intimidate",
                                            "effect": "Lowers opponents' Attack by one stage upon entering battle."}]


def test_an_ability_without_an_english_effect_keeps_its_row_with_no_effect():
    """New abilities often have no effect text yet in PokéAPI."""
    assert extract_ability({"id": 312, "name": "new-ability", "effect_entries": []}) == [
        {"ability_id": 312, "ability_name": "new-ability", "effect": None}]


def test_a_payload_without_an_id_is_an_error():
    with pytest.raises(KeyError):
        extract_ability({"name": "broken", "effect_entries": []})


NEW_MEGA_ABILITY = {"id": 312, "name": "new-ability", "effect_entries": []}


def _fetch(api, calls):
    def fetch(aid):
        calls.append(aid)
        if aid not in api:
            raise requests.HTTPError(f"404 Client Error for ability {aid}")
        return api[aid]
    return fetch


def _crawl(tmp_path, ids, api, calls):
    from python.crawl_data.data_ability import crawl_abilities
    return crawl_abilities(ids, _fetch(api, calls), tmp_path / "ability_raw.csv",
                           tmp_path / "ability_raw_failures.csv", tmp_path / "ability_raw_progress.csv", delay=0)


def test_failed_ids_land_in_the_failures_csv_and_a_rerun_resumes_and_retries_them(tmp_path):
    counts = _crawl(tmp_path, [22, 312], {22: INTIMIDATE}, [])
    assert counts == {"already_done": 0, "crawled": 1, "empty": 0, "failed": 1}
    failed = pd.read_csv(tmp_path / "ability_raw_failures.csv")
    assert failed["ability_id"].tolist() == [312] and "404" in failed["error"].iloc[0]
    calls = []
    counts = _crawl(tmp_path, [22, 312], {22: INTIMIDATE, 312: NEW_MEGA_ABILITY}, calls)
    assert calls == [312]                                                   # 22 was already crawled
    assert pd.read_csv(tmp_path / "ability_raw.csv")["ability_id"].tolist() == [22, 312]
    assert pd.read_csv(tmp_path / "ability_raw_failures.csv").empty         # this run's failures only
    assert counts["already_done"] == 1 and counts["failed"] == 0


def test_ids_in_an_ability_csv_written_by_the_old_crawler_count_as_done(tmp_path):
    """The old crawler wrote ability_raw.csv (ids 1..311) without a progress file: only new ids are fetched."""
    pd.DataFrame([(22, "intimidate", "x")], columns=["ability_id", "ability_name", "effect"]).to_csv(
        tmp_path / "ability_raw.csv", index=False)
    calls = []
    _crawl(tmp_path, [22, 312], {22: INTIMIDATE, 312: NEW_MEGA_ABILITY}, calls)
    assert calls == [312]


class _Response:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


def test_main_crawls_every_id_of_the_ability_list_without_touching_mysql(monkeypatch, tmp_path):
    from python.crawl_data import data_ability
    base = "https://pokeapi.co/api/v2/ability/"
    api = {f"{base}?limit=100000": {"results": [{"name": n, "url": f"{base}{i}/"}
                                               for n, i in (("new-ability", 312), ("intimidate", 22), ("gone", 404))]},
           f"{base}22/": INTIMIDATE, f"{base}312/": NEW_MEGA_ABILITY}
    monkeypatch.setattr(requests.Session, "get",
                        lambda self, url, timeout: _Response(200, api[url]) if url in api else _Response(404))
    sys.modules.pop("python.database.db_connection", None)
    out = tmp_path / "ability_raw.csv"
    assert data_ability.main(["--out", str(out), "--delay", "0"]) == 0
    assert pd.read_csv(out)["ability_id"].tolist() == [22, 312]
    assert pd.read_csv(tmp_path / "ability_raw_failures.csv")["ability_id"].tolist() == [404]
    assert pd.read_csv(tmp_path / "ability_raw_progress.csv")["ability_id"].tolist() == [22, 312]
    assert "python.database.db_connection" not in sys.modules


def test_importing_the_ability_and_type_crawlers_fetches_and_writes_nothing(monkeypatch, tmp_path):
    def no_network(*a, **k):
        raise AssertionError("network used on import")
    monkeypatch.setattr(requests.Session, "request", no_network)
    monkeypatch.setattr(requests, "get", no_network)
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("python.database.db_connection", None)
    for name in ("python.crawl_data.data_ability", "python.crawl_data.data_pokemon"):
        importlib.reload(importlib.import_module(name))
    assert list(tmp_path.iterdir()) == []
    assert "python.database.db_connection" not in sys.modules                 # MySQL only with --to-mysql
