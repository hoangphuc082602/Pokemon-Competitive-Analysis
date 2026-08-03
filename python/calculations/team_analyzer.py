from python.database.type_effectiveness_loader import (
    load_type_effectiveness
)
from python.database.types_loader import (
    load_all_types,
    get_type_data
)

# LOAD TYPE CHART
type_chart_df = load_type_effectiveness()
# LOAD TYPE
defender = get_type_data(
    load_all_types(),
    "type"
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


def get_type_effectiveness(
    type_chart_df,
    attacking_type,
    defending_type
):
    effectiveness = type_chart_df[
        (
            type_chart_df["attack_type"]
            == attacking_type.lower()
        )
        &
        (
            type_chart_df["defense_type"]
            == defending_type.lower()
        )
    ]
    if effectiveness.empty:
        return 1.0
    return float(
        effectiveness.iloc[0]["multiplier"]
    )


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
    attacking_type = (
        attacking_type.lower()
    )
    multiplier = 1.0
    defender_types = [
        t.lower()
        for t in defender["types"]
    ]

    # BASE TYPE CHART
    for defending_type in defender_types:
        multiplier *= (
            get_type_effectiveness(
                type_chart_df,
                attacking_type,
                defending_type
            )
        )

    # ABILITY IMMUNITY
    multiplier = (
        apply_ability_immunity(
            multiplier,
            attacking_type,
            defender
        )
    )
    if multiplier == 0:
        return 0.0

    # ABILITY RESISTANCE
    multiplier = (
        apply_ability_resistance(
            multiplier,
            attacking_type,
            defender
        )
    )

    return float(multiplier)