from python.calculations.team_type_analyzer import (
    analyze_team_offense,
    analyze_team_defense)
from python.calculations.team_synergy import (
    analyze_role_distribution,
    calculate_team_synergy
)
from python.recommendation.team_recommender import (
    detect_missing_roles,
    recommend_pokemon_for_roles
)


def analyze_team(team,type_chart_df):

    offense = analyze_team_offense(
        team,
        type_chart_df
    )
    defense = analyze_team_defense(
        team,
        type_chart_df
    )
    roles = analyze_role_distribution(
        team
    )
    synergy = calculate_team_synergy(
        offense,
        defense
    )
    missing_roles = detect_missing_roles(
        roles
    )
    recommendations = recommend_pokemon_for_roles(
        missing_roles
    )

    return {
        "offense": offense,
        "defense": defense,
        "roles": roles,
        "synergy_score": synergy,
        "recommendations":
            recommendations
    }