import math

def calculate_hp(
    base_hp,
    iv,
    ev,
    level
):
    return math.floor(
        (
            (
                2 * base_hp
                + iv
                + (ev / 4)
            ) * level
        ) / 100
    ) + level + 10

def calculate_other_stat(
    base_stat,
    iv,
    ev,
    level,
    nature_modifier
):
    return math.floor(
        (
            math.floor(
                (
                    (
                        2 * base_stat
                        + iv
                        + (ev / 4)
                    ) * level
                ) / 100
            ) + 5
        ) * nature_modifier
    )

def calculate_final_stats(
    base_stats,
    ivs,
    evs,
    level,
    nature_modifiers
):
    final_stats = {}

    final_stats["hp"] = calculate_hp(
        base_stats["hp"],
        ivs["hp"],
        evs["hp"],
        level
    )
    stat_names = [
        "atk",
        "def",
        "spatk",
        "spdef",
        "spe"
    ]
    for stat in stat_names:
        final_stats[stat] = calculate_other_stat(
            base_stats[stat],
            ivs[stat],
            evs[stat],
            level,
            nature_modifiers[stat]
        )

    return final_stats