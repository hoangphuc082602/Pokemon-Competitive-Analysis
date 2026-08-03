def detect_missing_roles(role_distribution):

    missing_roles = []

    if ("physical_sweeper"not in role_distribution):
        missing_roles.append(
            "physical_sweeper"
        )
    if ("special_sweeper"not in role_distribution):
        missing_roles.append(
            "special_sweeper"
        )
    if ("wall"not in role_distribution):
        missing_roles.append(
            "wall"
        )

    return missing_roles

def recommend_pokemon_for_roles(missing_roles, pokemon_database):

    recommended_pokemon = []

    for role in missing_roles:
        for pokemon in pokemon_database:
            if role in pokemon["roles"]:
                recommended_pokemon.append(
                    pokemon
                )

    return recommended_pokemon