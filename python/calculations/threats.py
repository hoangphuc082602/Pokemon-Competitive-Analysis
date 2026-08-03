def analyze_team_threats(weakness_result,meta_df):

    threats = []

    for pokemon_name in (meta_df["pokemon_name"].unique()):
        pokemon_types = (
            meta_df[
                meta_df["pokemon_name"]
                == pokemon_name
            ]["type"]
            .tolist()
        )
        
        threat_score = 0

        for pokemon_type in pokemon_types:
            threat_score += (
                weakness_result.get(
                    pokemon_type,
                    0
                )
            )
        threats.append({
            "pokemon": pokemon_name,
            "threat_score": threat_score
        })

    return sorted(
        threats,
        key=lambda x: x["threat_score"],
        reverse=True
    )