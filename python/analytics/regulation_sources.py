"""Game data source of each regulation (#37): which PokéAPI version group gives the learnsets of a regulation.

    gen9vgc*            -> scarlet-violet   (Scarlet / Violet VGC regulations)
    gen9championsvgc*   -> champions        (Pokémon Champions regulations; PokéAPI version group id 32, learn method train)

A regulation of no listed family raises UnmappedRegulationError: add its family here (and crawl its version group,
docs/ai-onboarding/04-WORKFLOWS.md) instead of falling back silently to another game's learnsets (BR-05).
Abilities are not split per game in PokéAPI: every gen 9 regulation uses the current abilities (past_abilities lists
abilities a Pokémon had up to an earlier generation, e.g. Gengar's Levitate up to generation VI, so none applies).
"""
from __future__ import annotations

import re

FAMILIES = ((re.compile(r"gen9vgc\d{4}reg[a-z0-9-]+"), "scarlet-violet"),
            (re.compile(r"gen9championsvgc\d{4}reg[a-z0-9-]+"), "champions"))
VERSION_GROUPS = tuple(dict.fromkeys(g for _, g in FAMILIES))   # every version group a regulation can use


def learnset_name(group: str) -> str:
    """File stem in data/raw and MySQL table of a version group's crawled learnsets (data_poke_move): pokemon_moves for
    scarlet-violet, pokemon_moves_<group> otherwise (e.g. pokemon_moves_champions)."""
    return "pokemon_moves" if group == "scarlet-violet" else f"pokemon_moves_{group.replace('-', '_')}"


class UnmappedRegulationError(ValueError):
    """A regulation of no family in FAMILIES."""


def version_group(regulation: str) -> str:
    """PokéAPI version group of `regulation`'s learnsets; UnmappedRegulationError when its family is not listed."""
    for pattern, group in FAMILIES:
        if pattern.fullmatch(regulation):
            return group
    raise UnmappedRegulationError(f"regulation {regulation!r} has no game data source (version group): "
                                  f"add its family to python/analytics/regulation_sources.py")
