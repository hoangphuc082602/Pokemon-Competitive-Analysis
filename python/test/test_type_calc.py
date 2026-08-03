from python.database.type_effectiveness_loader import (
    load_type_effectiveness
)

from python.database.pokemon_loader import (
    load_all_pokemon_stats
)

from python.database.moves_loader import (
    load_all_moves,
    get_move_data
)

from python.database.natures_loader import (
    load_all_natures
)

from python.models.team_builder import (
    build_pokemon
)

from python.calculations.type_calc import (
    calculate_type_multiplier
)

# =====================================================
# LOAD DATA
# =====================================================

type_chart_df = load_type_effectiveness()
pokemon_df = load_all_pokemon_stats()
moves_df = load_all_moves()
nature_df = load_all_natures()

# =====================================================
# TEAM MEMBERS
# =====================================================

charizard = build_pokemon(
    pokemon_df,
    nature_df,
    pokemon_name="charizard",
    level=50,
    nature="timid",
    ability="blaze",
    item="charizardite-y",
    moves=[
        "flamethrower",
        "air-slash",
        "focus-blast",
        "solar-beam"
    ],
    ivs={
        "hp":31,
        "atk":31,
        "def":31,
        "spatk":31,
        "spdef":31,
        "spe":31
    },
    evs={
        "hp":0,
        "atk":0,
        "def":4,
        "spatk":252,
        "spdef":0,
        "spe":252
    }
)

venusaur = build_pokemon(
    pokemon_df,
    nature_df,
    pokemon_name="venusaur",
    level=50,
    nature="modest",
    ability="chlorophyll",
    item="life-orb",
    moves=[
        "sludge-bomb",
        "giga-drain",
        "earth-power",
        "sleep-powder"
    ],
    ivs={
        "hp":31,
        "atk":0,
        "def":31,
        "spatk":31,
        "spdef":31,
        "spe":31
    },
    evs={
        "hp":4,
        "atk":0,
        "def":0,
        "spatk":252,
        "spdef":0,
        "spe":252
    }
)

team = [
    charizard,
    venusaur
]

# =====================================================
# TEST 1
# Flamethrower -> Venusaur
# Fire vs Grass/Poison
# Expected = 2x
# =====================================================

move = get_move_data(
    moves_df,
    "flamethrower"
)

multiplier = calculate_type_multiplier(
    type_chart_df,
    charizard,
    venusaur,
    move
)

print("=" * 50)
print("TEST 1")
print("Charizard Flamethrower -> Venusaur")
print("Expected: 2")
print("Actual:", multiplier)

# =====================================================
# TEST 2
# Solar Beam -> Venusaur
# Grass vs Grass/Poison
# Expected = 0.25
# =====================================================

move = get_move_data(
    moves_df,
    "solar-beam"
)

multiplier = calculate_type_multiplier(
    type_chart_df,
    charizard,
    venusaur,
    move
)

print("=" * 50)
print("TEST 2")
print("Charizard Solar Beam -> Venusaur")
print("Expected: 0.25")
print("Actual:", multiplier)

# =====================================================
# TEST 3
# Earth Power -> Charizard
# Ground vs Fire/Flying
# Expected = 0
# Flying immunity
# =====================================================

move = get_move_data(
    moves_df,
    "earth-power"
)

multiplier = calculate_type_multiplier(
    type_chart_df,
    venusaur,
    charizard,
    move
)

print("=" * 50)
print("TEST 3")
print("Venusaur Earth Power -> Charizard")
print("Expected: 0")
print("Actual:", multiplier)