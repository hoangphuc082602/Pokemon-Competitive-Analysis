"""Crawl PokéAPI learnsets per /pokemon entry -> data/raw/pokemon_moves.csv (pokemon_id, move_id, learn_method,
level_learned), Scarlet / Violet version group only (choosing it per regulation: #37).

    python -m python.crawl_data.data_poke_move                    # every /pokemon entry, incl. alternate forms (ids >= 10001)
    python -m python.crawl_data.data_poke_move --ids 6 10034      # small test range (add --to-mysql to load MySQL)

pokemon_id is the PokéAPI /pokemon id, so alternate forms get their own learnset (#36). A form with no Scarlet /
Violet move (e.g. Mega forms) has no rows; pokemon_moves_progress.csv records it with rows = 0, and calc_master then
borrows the default form's learnset. Resumable, retried with backoff, failures in pokemon_moves_failures.csv: see
python/crawl_data/pokeapi_crawl.py. With --to-mysql the MySQL table pokemon_moves is rebuilt from the full CSV.
"""
from __future__ import annotations

from pathlib import Path

from python.crawl_data.pokeapi_crawl import ref_id, run_cli

VERSION_GROUP = "scarlet-violet"
COLUMNS = ["pokemon_id", "move_id", "learn_method", "level_learned"]


def extract_moves(data: dict, version_group: str = VERSION_GROUP) -> list[dict]:
    """Learnset rows of one /pokemon response in `version_group`."""
    return [{"pokemon_id": int(data["id"]), "move_id": ref_id(m["move"]),
             "learn_method": ref_id(d["move_learn_method"]), "level_learned": int(d["level_learned_at"])}
            for m in data["moves"] for d in m["version_group_details"]
            if d["version_group"]["name"] == version_group]


def main(argv=None) -> int:
    return run_cli(argv, __doc__, extract_moves, COLUMNS, Path("data/raw/pokemon_moves.csv"), "pokemon_moves")


if __name__ == "__main__":
    raise SystemExit(main())
