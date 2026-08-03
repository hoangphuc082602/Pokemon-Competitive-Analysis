from python.calculations.team_type_analyzer import (
    analyze_team_offense,
    analyze_team_defense
)
from python.database.type_effectiveness_loader import (
    load_type_effectiveness
)
type_chart_df = (
    load_type_effectiveness()
)

team = [
    {
        "name": "rotom-wash",
        "types": [
            "electric",
            "water"
        ],
        "ability": "levitate",
        "item": "leftovers"
    },

    {
        "name": "garchomp",
        "types": [
            "dragon",
            "ground"
        ],
        "ability": "rough-skin",
        "item": "choice-scarf"
    },

    {
        "name": "scizor",
        "types": [
            "bug",
            "steel"
        ],
        "ability": "technician",
        "item": "life-orb"
    }
]

# OFFENSIVE
offense = analyze_team_offense(
    type_chart_df,
    team
)
print(offense["ground"])

# DEFENSIVE
defense = analyze_team_defense(
    type_chart_df,
    team
)
print(defense["fire"])