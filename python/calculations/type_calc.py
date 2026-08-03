# DEFENSIVE ABILITIES
DEFENSIVE_ABILITY_IMMUNITIES = {
    "levitate": ["ground"],
    "flash-fire": ["fire"],
    "water-absorb": ["water"],
    "volt-absorb": ["electric"],
    "lightning-rod": ["electric"],
    "motor-drive": ["electric"],
    "sap-sipper": ["grass"],
    "storm-drain": ["water"],
    "dry-skin": ["water"],
    "earth-eater": ["ground"],
    "well-baked-body": ["fire"],
    "wind-rider": ["flying"]
}

DEFENSIVE_ABILITY_RESISTANCES = {
    "thick-fat": {
        "fire": 0.5,
        "ice": 0.5
    },
    "heatproof": {
        "fire": 0.5
    },
    "purifying-salt": {
        "ghost": 0.5
    }
}

# OFFENSIVE ABILITIES
OFFENSIVE_ABILITY_BYPASS = {

    "scrappy": {
        "normal": ["ghost"],
        "fighting": ["ghost"]
    }
}

OFFENSIVE_TYPE_OVERRIDE = {
    "normalize": "normal",
    "pixilate": "fairy",
    "refrigerate": "ice",
    "aerilate": "flying",
    "galvanize": "electric"
}

# BASE TYPE LOOKUP
def get_type_multiplier(type_chart_df,attack_type,defense_type):
    result = type_chart_df[
        (type_chart_df["attack_type"]== attack_type.lower())
        &
        (type_chart_df["defense_type"]== defense_type.lower())
    ]
    if result.empty:
        return 1.0
    return float(
        result.iloc[0]["multiplier"]
    )

# TYPE OVERRIDE
def get_actual_move_type(attacker,move):
    move_type = (
        move["type"]
        .lower()
    )
    ability = (
        attacker["ability"]
        .lower()
    )
    if (move_type == "normal"
        and
        ability in OFFENSIVE_TYPE_OVERRIDE):
        return OFFENSIVE_TYPE_OVERRIDE[ability]
    return move_type

# SCRAPPY
def bypass_immunity(
    attacker,
    move_type,
    defense_type
):
    ability = (
        attacker["ability"]
        .lower()
    )
    bypass_map = (
        OFFENSIVE_ABILITY_BYPASS
        .get(ability,{})
    )
    ignored_types = (
        bypass_map
        .get(
            move_type,
            []
        )
    )
    return (
        defense_type
        in ignored_types
    )

# IMMUNITY CHECK
def apply_defensive_immunity(
    move_type,
    defender
):
    ability = (
        defender["ability"]
        .lower()
    )
    immune_types = (
        DEFENSIVE_ABILITY_IMMUNITIES
        .get(
            ability,
            []
        )
    )
    if move_type in immune_types:
        return 0.0
    return None

# RESISTANCE CHECK
def apply_defensive_resistance(
    multiplier,
    move_type,
    defender
):
    ability = (
        defender["ability"]
        .lower()
    )
    resist_map = (
        DEFENSIVE_ABILITY_RESISTANCES
        .get(
            ability,
            {}
        )
    )
    if move_type in resist_map:
        multiplier *= (
            resist_map[
                move_type
            ]
        )
    return multiplier

# MAIN FUNCTION
def calculate_type_multiplier(
    type_chart_df,
    attacker,
    defender,
    move
):
    move_type = (
        get_actual_move_type(
            attacker,
            move
        )
    )
    attacker_ability = (
        attacker["ability"]
        .lower()
    )
    multiplier = 1.0

    # TYPE CHART
    for defense_type in defender["types"]:
        if defense_type is None:
            continue
        defense_type = (
            defense_type.lower()
        )
        type_multiplier = (
            get_type_multiplier(
                type_chart_df,
                move_type,
                defense_type
            )
        )

        # SCRAPPY
        if (
            type_multiplier == 0
            and
            bypass_immunity(
                attacker,
                move_type,
                defense_type
            )
        ):
            type_multiplier = 1
        multiplier *= (
            type_multiplier
        )

    # MOLD BREAKER
    if (
        attacker_ability
        != "mold-breaker"
    ):
        immunity_result = (
            apply_defensive_immunity(
                move_type,
                defender
            )
        )
        if immunity_result == 0:
            return 0.0
        multiplier = (
            apply_defensive_resistance(
                multiplier,
                move_type,
                defender
            )
        )
    return float(
        multiplier
    )