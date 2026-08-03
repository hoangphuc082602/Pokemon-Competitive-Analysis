from python.calculations.type_calc import (
    calculate_type_multiplier
)

ABILITY_IMMUNITIES = {
    "levitate": ["ground"],
    "flash-fire": ["fire"],
    "water-absorb": ["water"],
    "volt-absorb": ["electric"],
    "lightning-rod": ["electric"],
    "motor-drive": ["electric"],
    "sap-sipper": ["grass"],
    "storm-drain": ["water"],
    "dry-skin": ["water"],
    "earth-eater": ["ground"]
}

ABILITY_RESISTANCE = {
    "thick-fat": {
        "fire": 0.5,
        "ice": 0.5
    },
    "heatproof": {
        "fire": 0.5
    }
}


def apply_ability_immunity(
    multiplier,
    attacking_type,
    defender
):
    ability = (
        defender.get("ability", "")
        .lower()
    )
    immune_types = (
        ABILITY_IMMUNITIES
        .get(ability, [])
    )
    if attacking_type in immune_types:
        return 0.0
    return multiplier


def apply_ability_resistance(
    multiplier,
    attacking_type,
    defender
):
    ability = (
        defender.get("ability", "")
        .lower()
    )
    resist_map = (
        ABILITY_RESISTANCE
        .get(ability, {})
    )

    if attacking_type in resist_map:
        multiplier *= (
            resist_map[attacking_type]
        )
    return multiplier


def calculate_total_multiplier(
    type_chart_df,
    attacking_type,
    defender
):
    multiplier = (
        calculate_type_multiplier(
            type_chart_df,
            attacking_type,
            defender["types"]
        )
    )
    multiplier = (
        apply_ability_immunity(
            multiplier,
            attacking_type,
            defender
        )
    )

    if multiplier == 0:
        return 0.0
    multiplier = (
        apply_ability_resistance(
            multiplier,
            attacking_type,
            defender
        )
    )
    return float(multiplier)