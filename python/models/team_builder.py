from python.calculations.nature_calc import (get_nature_modifiers)
from python.calculations.stats_calc import (calculate_final_stats)
from python.database.pokemon_loader import (get_pokemon_stats)

def build_pokemon(
    pokemon_df,
    nature_df,
    pokemon_name,
    level,
    nature,
    ability,
    item,
    moves,
    ivs,
    evs
):

    # BASE STATS
    base_stats = get_pokemon_stats(
        pokemon_df,
        pokemon_name
    )

    # NATURE MODIFIERS
    nature_modifiers = (
        get_nature_modifiers(
            nature_df,
            nature
        )
    )

    # FINAL STATS
    final_stats = calculate_final_stats(
        base_stats,
        ivs,
        evs,
        level,
        nature_modifiers
    )

    # BUILD OBJECT
    pokemon_object = {
        "name": pokemon_name,
        "types": [
            base_stats["type_1"],
            base_stats["type_2"]
        ],
        "level": level,
        "nature": nature,
        "ability": ability,
        "item": item,
        "moves": moves,
        "ivs": ivs,
        "evs": evs,
        "stats": final_stats
    }
    return pokemon_object