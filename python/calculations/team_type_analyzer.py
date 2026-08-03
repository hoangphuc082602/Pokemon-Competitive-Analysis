from python.calculations.type_calc import (
    calculate_type_multiplier
)
from python.calculations.battle_type_calc import (
    calculate_total_multiplier
)
from python.database.type_effectiveness_loader import (
    load_type_effectiveness
)

# LOAD TYPE CHART
type_chart_df = load_type_effectiveness()

# CLASSIFY MULTIPLIER
def classify_multiplier(multiplier):
    if multiplier == 4:
        return "4x"
    elif multiplier == 2:
        return "2x"
    elif multiplier == 1:
        return "1x"
    elif multiplier == 0.5:
        return "0.5x"
    elif multiplier == 0.25:
        return "0.25x"
    elif multiplier == 0:
        return "0x"
    return "other"

# OFFENSIVE ANALYZER
def analyze_team_offense(
    type_chart_df,
    team
):
    all_types = sorted(
        type_chart_df["defense_type"]
        .unique()
        .tolist()
    )
    result = {}
    for attack_type in all_types:
        analysis = {
            "super_effective": [],
            "neutral": [],
            "not_effective": [],
            "immune": []
        }
        for defense_type in all_types:
            multiplier = (
                calculate_type_multiplier(
                    type_chart_df,
                    attack_type,
                    [defense_type]
                )
            )
            if multiplier > 1:
                analysis[
                    "super_effective"
                ].append(defense_type)
            elif multiplier == 1:
                analysis[
                    "neutral"
                ].append(defense_type)
            elif multiplier == 0:
                analysis[
                    "immune"
                ].append(defense_type)
            else:
                analysis[
                    "not_effective"
                ].append(defense_type)
        result[attack_type] = analysis
    return result

# DEFENSIVE ANALYZER
def analyze_team_defense(
    type_chart_df,
    team
):
    all_attack_types = sorted(
        type_chart_df["attack_type"]
        .unique()
        .tolist()
    )
    result = {}
    for attack_type in all_attack_types:
        analysis = {
            "4x": [],
            "2x": [],
            "1x": [],
            "0.5x": [],
            "0.25x": [],
            "0x": []
        }
        for pokemon in team:
            multiplier = (
                calculate_total_multiplier(
                    type_chart_df,
                    attack_type,
                    pokemon
                )
            )
            bucket = classify_multiplier(
                multiplier
            )
            if bucket in analysis:
                analysis[bucket].append({
                    "pokemon": pokemon["name"],
                    "multiplier": multiplier
                })
        result[attack_type] = analysis
    return result