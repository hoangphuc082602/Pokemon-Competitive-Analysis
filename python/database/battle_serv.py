from python.database.pokemon_loader import (
    load_pokemon_stats,
    load_pokemon_types
)

from python.database.moves_loader import (
    load_move
)

from python.calculations.stats_calc import (
    all_stats_calc
)

from python.calculations.damage_calc import (
    calculate_damage
)

from python.calculations.nature_calc import (
    get_nature_modifiers
)


def pokemon_attack(
    attacker_name,
    defender_name,
    move_name,

    attacker_ivs,
    attacker_evs,
    attacker_nature,

    defender_ivs,
    defender_evs,
    defender_nature,

    level=50
):

    # LOAD POKEMON
    attacker_base = load_pokemon_stats(
        attacker_name
    )

    defender_base = load_pokemon_stats(
        defender_name
    )

    # LOAD TYPES
    attacker_types = load_pokemon_types(
        attacker_name
    )

    defender_types = load_pokemon_types(
        defender_name
    )

    # LOAD MOVE
    move = load_move(move_name)

    # NATURE
    attacker_nature_mod = get_nature_modifiers(
        attacker_nature
    )

    defender_nature_mod = get_nature_modifiers(
        defender_nature
    )

    # FINAL STATS
    attacker_stats = all_stats_calc(
        attacker_base,
        attacker_ivs,
        attacker_evs,
        level,
        attacker_nature_mod
    )

    defender_stats = all_stats_calc(
        defender_base,
        defender_ivs,
        defender_evs,
        level,
        defender_nature_mod
    )

    # DETERMINE ATTACK/DEFENSE STATS
    if move["damage_class_name"] == "physical":

        attack_stat = attacker_stats["atk"]
        defense_stat = defender_stats["def"]

    else:

        attack_stat = attacker_stats["spatk"]
        defense_stat = defender_stats["spdef"]

    # STAB
    stab = (
        move["type_name"]
        in attacker_types
    )

    result = calculate_damage(
        level=level,
        power=move["power"],
        attack=attack_stat,
        defense=defense_stat,
        attack_type=move["type_name"],
        defender_types=defender_types,
        stab=stab
    )

    return result