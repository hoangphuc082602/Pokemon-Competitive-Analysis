from python.database.pokemon_loader import (
    load_all_pokemon_stats,
    get_pokemon_stats
)

from python.database.moves_loader import (
    load_all_moves,
    get_move_data
)

from python.database.natures_loader import (
    load_all_natures,
    get_nature_data
)

from python.database.type_effectiveness_loader import (
    load_type_effectiveness,
    get_type_effectiveness
)

from python.calculations.nature_calc import (
    get_nature_modifiers
)

from python.calculations.stats_calc import (
    calculate_final_stats
)

from python.calculations.damage_calc import (
    calculate_damage
)

# LOAD DATA ONCE
pokemon_df = load_all_pokemon_stats()
move_df = load_all_moves()
nature_df = load_all_natures()
type_chart_df = load_type_effectiveness()

# GET POKEMON
garchomp = get_pokemon_stats(
    pokemon_df,
    "garchomp"
)

# GET MOVE
earthquake = get_move_data(
    move_df,
    "earthquake"
)

# NATURE
nature_modifiers = get_nature_modifiers(
    nature_df,
    "jolly"
)

# IVS / EVS
ivs = {
    "hp": 31,
    "atk": 31,
    "def": 31,
    "spatk": 31,
    "spdef": 31,
    "spe": 31
}

evs = {
    "hp": 0,
    "atk": 252,
    "def": 0,
    "spatk": 0,
    "spdef": 4,
    "spe": 252
}

# FINAL STATS
final_stats = calculate_final_stats(
    garchomp,
    ivs,
    evs,
    level=50,
    nature_modifiers=nature_modifiers
)

print(final_stats)

# DAMAGE TEST
damage = calculate_damage(
    type_chart_df=type_chart_df,
    level=50,
    power=earthquake["power"],
    attack=final_stats["atk"],
    defense=120,
    attack_type="Ground",
    defender_types=["Steel"],
    stab=True
)

print(damage)