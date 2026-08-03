def build_team_features(team_analysis):
    features = {
        "synergy_score":
            team_analysis[
                "synergy_score"
            ],
        "weakness_total":
            sum(
                team_analysis[
                    "weakness"
                ].values()
            ),
        "resistance_total":
            sum(
                team_analysis[
                    "resistance"
                ].values()
            )
    }
    return features