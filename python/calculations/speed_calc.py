from python.calculations.stats_calc import (calculate_other_stat)


# Keys are PokéAPI item slugs; "Choice Scarf" / "choice_scarf" are accepted too (see normalize_item_name).
ITEM_SPEED_MODIFIER = {
    "choice-scarf": 1.5,
    "iron-ball": 0.5
}


def normalize_item_name(item_name):
    """'Choice Scarf' / 'choice_scarf' / 'choice-scarf' -> 'choice-scarf'."""
    return str(item_name or "").strip().lower().replace(" ", "-").replace("_", "-")


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

    item = normalize_item_name(item_name)
    if item in ITEM_SPEED_MODIFIER:
        speed = int(
            speed
            * ITEM_SPEED_MODIFIER[item]
        )

    return speed
