from calculations.role_label import (label_role)

def analyze_role_distribution(team):

    role_result = {}

    for pokemon in team:
        role = label_role(
            pokemon
        )
        if role not in role_result:
            role_result[role] = 0
        role_result[role] += 1

    return role_result

def calculate_team_synergy(weakness_result,resistance_result):

    total_weakness = sum(weakness_result.values())
    total_resistance = sum(resistance_result.values())

    synergy_score = (
        total_resistance
        - total_weakness
    )

    return synergy_score

