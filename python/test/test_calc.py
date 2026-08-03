from python.calculations.stats_calc import all_stats_calc
base_stats = {
    "hp": 108,
    "attack": 130,
    "defense": 95,
    "sp_attack": 80,
    "sp_defense": 85,
    "speed": 102
}

ivs = {
    "hp": 31,
    "attack": 31,
    "defense": 31,
    "sp_attack": 31,
    "sp_defense": 31,
    "speed": 31
}

evs = {
    "hp": 0,
    "attack": 252,
    "defense": 0,
    "sp_attack": 0,
    "sp_defense": 4,
    "speed": 252
}

nature_modifiers = {
    "attack": 1.0,
    "defense": 1.0,
    "sp_attack": 0.9,
    "sp_defense": 1.0,
    "speed": 1.1
}

stats = all_stats_calc(
    base_stats,
    ivs,
    evs,
    level=50,
    nature_multiplier=nature_modifiers
)

print(stats)