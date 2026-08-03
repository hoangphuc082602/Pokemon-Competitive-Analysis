from python.calculations.stats_calc import (calculate_other_stat)


ITEM_SPEED_MODIFIER = {
    "Choice Scarf": 1.5,
    "Iron Ball": 0.5
}


def calculate_speed(
    base_speed,
    iv,
    ev,
    level,
    nature_modifier,
    item_name=None
):
    speed = calculate_other_stat(
        base_speed,
        iv,
        ev,
        level,
        nature_modifier
    )

    if item_name in ITEM_SPEED_MODIFIER:
        speed = int(
            speed
            * ITEM_SPEED_MODIFIER[item_name]
        )

    return speed