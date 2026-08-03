import math
import random

from python.calculations.type_calc import (calculate_total_multiplier)

def calculate_damage(
    type_chart_df,
    level,
    power,
    attack,
    defense,
    attack_type,
    defender_types,
    stab=False
):
    base_damage = (
        (
            (
                (
                    (2 * level)
                    / 5
                ) + 2
            )
            * power
            * attack
            / defense
        ) / 50
    ) + 2

    stab_modifier = 1.5 if stab else 1

    type_modifier = calculate_total_multiplier(
        type_chart_df,
        attack_type,
        defender_types
    )

    random_modifier = random.uniform(
        0.85,
        1
    )

    damage = math.floor(
        base_damage
        * stab_modifier
        * type_modifier
        * random_modifier
    )
    return {
        "damage": damage,
        "type_modifier": type_modifier
    }