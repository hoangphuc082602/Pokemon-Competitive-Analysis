import json
from python.database.type_effectiveness_loader import (
    load_type_effectiveness
)
from python.database.pokemon_loader import (
    load_all_pokemon_stats
)
from python.database.moves_loader import (
    load_all_moves
)
from python.database.natures_loader import (
    load_all_natures
)
from python.models.team_builder import (
    build_pokemon
)
from python.calculations.atk_balance import (
    analyze_damage_profile
)

# LOAD DATA
type_chart_df = load_type_effectiveness()
pokemon_df = load_all_pokemon_stats()
moves_df = load_all_moves()
nature_df = load_all_natures()

# IV TEMPLATE
perfect_ivs = {
    "hp": 31,
    "atk": 31,
    "def": 31,
    "spatk": 31,
    "spdef": 31,
    "spe": 31
}

# BUILD TEAM
charizard = build_pokemon(
    pokemon_df = pokemon_df,
    nature_df = nature_df,
    pokemon_name = "charizard",
    level = 50,
    nature = "timid",
    ability = "blaze",
    item = "charizardite-y",
    moves = [
        "flamethrower",
        "air-slash",
        "focus-blast",
        "solar-beam"
    ],
    ivs = perfect_ivs,
    evs = {
        "hp": 0,
        "atk": 0,
        "def": 4,
        "spatk": 252,
        "spdef": 0,
        "spe": 252
    }
)

venusaur = build_pokemon(
    pokemon_df = pokemon_df,
    nature_df = nature_df,
    pokemon_name = "venusaur",
    level = 50,
    nature = "modest",
    ability = "chlorophyll",
    item = "life-orb",
    moves = [
        "sludge-bomb",
        "giga-drain",
        "earth-power",
        "sleep-powder"
    ],
    ivs = perfect_ivs,
    evs = {
        "hp": 4,
        "atk": 0,
        "def": 0,
        "spatk": 252,
        "spdef": 0,
        "spe": 252
    }
)

garchomp = build_pokemon(
    pokemon_df = pokemon_df,
    nature_df = nature_df,
    pokemon_name = "garchomp",
    level = 50,
    nature = "jolly",
    ability = "rough-skin",
    item = "rocky-helmet",
    moves = [
        "earthquake",
        "dragon-claw",
        "stone-edge",
        "fire-fang"
    ],
    ivs = perfect_ivs,
    evs = {
        "hp": 0,
        "atk": 252,
        "def": 0,
        "spatk": 0,
        "spdef": 4,
        "spe": 252
    }
)
team = [
    charizard,
    venusaur,
    garchomp
]

# ANALYZE DAMAGE PROFILE
damage_profile = analyze_damage_profile(
    team = team,
    move_df = moves_df
)
print(json.dumps(damage_profile, indent=4))