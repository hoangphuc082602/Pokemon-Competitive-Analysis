"""Crawl PokéAPI learnsets per /pokemon entry, one PokéAPI version group per run (#37), into
data/raw/pokemon_moves.csv (scarlet-violet) or data/raw/pokemon_moves_<version group>.csv (e.g. champions):
pokemon_id, move_id, learn_method, level_learned.

    python -m python.crawl_data.data_poke_move                                # scarlet-violet, every /pokemon entry
    python -m python.crawl_data.data_poke_move --version-group champions      # Pokémon Champions (learn method train)
    python -m python.crawl_data.data_poke_move --ids 6 10034                  # small test range (add --to-mysql to load MySQL)

--version-group (not listed by --help) takes the version groups of python/analytics/regulation_sources.py (the game of each regulation).
pokemon_id is the PokéAPI /pokemon id, so alternate forms get their own learnset (#36). A form with no move in the
version group (e.g. Mega forms in scarlet-violet) has no rows; the progress CSV records it with rows = 0, and
calc_master then borrows another learnset and says which. Resumable, retried with backoff, failures in
<out>_failures.csv: see python/crawl_data/pokeapi_crawl.py. With --to-mysql the MySQL table pokemon_moves
(scarlet-violet) or pokemon_moves_<version group> is rebuilt from the full CSV.
"""
from __future__ import annotations

import argparse
from functools import partial
from pathlib import Path

from python.analytics.regulation_sources import VERSION_GROUPS, learnset_name
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
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--version-group", choices=VERSION_GROUPS, default=VERSION_GROUP)
    known, rest = pre.parse_known_args(argv)
    name = learnset_name(known.version_group)
    return run_cli(rest, __doc__, partial(extract_moves, version_group=known.version_group), COLUMNS,
                   Path(f"data/raw/{name}.csv"), name)


if __name__ == "__main__":
    raise SystemExit(main())
