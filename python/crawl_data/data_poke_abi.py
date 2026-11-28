"""Crawl PokéAPI abilities per /pokemon entry -> data/raw/pokemon_ability.csv (pokemon_id, abi_id, hidden_abi).

    python -m python.crawl_data.data_poke_abi                     # every /pokemon entry, incl. alternate forms (ids >= 10001)
    python -m python.crawl_data.data_poke_abi --ids 6 10034       # small test range (add --to-mysql to load MySQL)

pokemon_id is the PokéAPI /pokemon id, so alternate forms (e.g. charizard-mega-x = 10034) get their own abilities
(#36). Some new forms have no ability in PokéAPI yet (e.g. zygarde-mega = 10301): no rows, recorded with rows = 0
in pokemon_ability_progress.csv (calc_master then borrows the default form's abilities). Resumable, retried with backoff, failures in
pokemon_ability_failures.csv: see python/crawl_data/pokeapi_crawl.py. With --to-mysql the MySQL table
pokemon_abilities is rebuilt from the full CSV.
"""
from __future__ import annotations

from pathlib import Path

from python.crawl_data.pokeapi_crawl import ref_id, run_cli

COLUMNS = ["pokemon_id", "abi_id", "hidden_abi"]


def extract_abilities(data: dict) -> list[dict]:
    """Ability rows of one /pokemon response; none when PokéAPI lists no ability (a missing list is a KeyError)."""
    return [{"pokemon_id": int(data["id"]), "abi_id": ref_id(a["ability"]),
             "hidden_abi": bool(a["is_hidden"])} for a in data["abilities"]]


def main(argv=None) -> int:
    return run_cli(argv, __doc__, extract_abilities, COLUMNS, Path("data/raw/pokemon_ability.csv"),
                   "pokemon_abilities")


if __name__ == "__main__":
    raise SystemExit(main())
