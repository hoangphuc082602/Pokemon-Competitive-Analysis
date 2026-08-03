import math
import random
from python.calculations.type_calc import (
    calculate_type_multiplier
)
from python.calculations.get_battle_stats import (
    get_battle_stats
)
from python.calculations.stab_modifier import (
    get_stab_modifier
)
from python.calculations.base_damage import (
    calc_base_damage
)
from python.calculations.percentage_ko import (
    calculate_ohko_chance,
    calculate_2hko_chance
)

# DAMAGE CALC
def calculate_damage(
    attacker,
    defender,
    move,
    type_chart_df
):

    # GET STATS
    attack_stat, defense_stat = (
        get_battle_stats(
            attacker,
            defender,
            move
        )
    )

    # BASE DAMAGE
    base_damage = calc_base_damage(
        attacker=attacker,
        move=move,
        attack_stat=attack_stat,
        defense_stat=defense_stat
    )

    # STAB
    stab_modifier = get_stab_modifier(
        attacker,
        move
    )

    # TYPE
    type_modifier = (
        calculate_type_multiplier(
            type_chart_df,
            attacker,
            defender,
            move
        )
    )

    # RANDOM
    random_modifier = random.uniform(
        0.85,
        1
    )

    # FINAL DAMAGE
    final_damage = math.floor(
        base_damage
        * stab_modifier
        * type_modifier
        * random_modifier
    )

    # MIN DAMAGE
    min_damage = math.floor(
        base_damage
        * stab_modifier
        * type_modifier
        * 0.85
    )

    #MAX DAMAGE
    max_damage = math.floor(
        base_damage
        * stab_modifier
        * type_modifier
    )

    # OHKO CHANCE
    ohko_chance = calculate_ohko_chance(
        min_damage,
        max_damage,
        defender["stats"]["hp"]
    )

    # 2HKO CHANCE
    two_hko_chance = calculate_2hko_chance(
        min_damage,
        max_damage,
        defender["stats"]["hp"]
    )

    # DAMAGE %
    damage_percent = (
        final_damage
        / defender["stats"]["hp"]
    ) * 100

    return {
        "damage": final_damage,
        "damage_percent": round(
            damage_percent,
            2
        ),
        "min_damage": min_damage,
        "max_damage": max_damage,
        "ohko_chance": round(
            ohko_chance,
            2
        ),
        "two_hko_chance": round(
            two_hko_chance,
            2
        ),
        "type_modifier": type_modifier,
        "stab": stab_modifier,
        "category": move["damage_class"]
    }