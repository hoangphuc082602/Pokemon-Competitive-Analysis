from python.database.pokemon_loader import (
    load_all_pokemon_stats
)
from python.database.natures_loader import (
    load_all_natures
)
from python.database.moves_loader import (
    load_all_moves,
    get_move_data
)
from python.database.type_effectiveness_loader import (
    load_type_effectiveness,
    get_type_effectiveness
)
from python.models.team_builder import (
    build_pokemon
)
from python.calculations.damage_calc_v2 import (
    calculate_damage
)

# LOAD DATA
pokemon_df = load_all_pokemon_stats()
nature_df = load_all_natures()
move_df = load_all_moves()
type_chart_df = load_type_effectiveness()

# IVS / EVS
ivs = {
    "hp": 31,
    "atk": 31,
    "def": 31,
    "spatk": 31,
    "spdef": 31,
    "spe": 31
}

# GARCHOMP
garchomp = build_pokemon(
    pokemon_df= pokemon_df,
    nature_df= nature_df,
    pokemon_name= "garchomp",
    level= 50,
    nature= "jolly",
    ability= "rough skin",
    item= "choice scarf",
    moves= [
        "earthquake"
    ],
    ivs= ivs,
    evs= {
        "hp": 0,
        "atk": 252,
        "def": 0,
        "spatk": 0,
        "spdef": 4,
        "spe": 252
    }
)

# Blaziken
blaziken = build_pokemon(
    pokemon_df= pokemon_df,
    nature_df= nature_df,
    pokemon_name= "blaziken",
    level= 50,
    nature= "impish",
    ability= "speed boost",
    item= "leftovers",
    moves= [],
    ivs= ivs,
    evs= {
        "hp": 252,
        "atk": 0,
        "def": 252,
        "spatk": 0,
        "spdef": 4,
        "spe": 0
    }
)

# MOVE
earthquake = get_move_data(
    move_df,
    "earthquake"
)

# DAMAGE
damage = calculate_damage(
    attacker= garchomp,
    defender= blaziken,
    move= earthquake,
    type_chart_df= type_chart_df
)
print(damage)