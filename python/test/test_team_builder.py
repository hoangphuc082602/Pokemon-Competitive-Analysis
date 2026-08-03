from python.database.pokemon_loader import (
    load_all_pokemon_stats
)
from python.database.natures_loader import (
    load_all_natures
)
from python.models.team_builder import (
    build_pokemon
)

# LOAD DATA
pokemon_df = load_all_pokemon_stats()
nature_df = load_all_natures()

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

# BUILD POKEMON
rottom = build_pokemon(
    pokemon_df= pokemon_df,
    nature_df= nature_df,
    pokemon_name= "rottom",
    level= 50,
    nature= "jolly",
    ability= "levitate",
    item= "choice scarf",
    moves= [
        "earthquake",
        "dragon claw",
        "protect",
        "rock slide"
    ],
    ivs= ivs,
    evs= evs
)

print(rottom)