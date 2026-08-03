def check_duplicate_items(team):

    items = []
    duplicate_items = []

    for pokemon in team:
        item = pokemon["item"]
        if item in items:
            duplicate_items.append(item)
        else:
            items.append(item)
    return duplicate_items

def check_duplicate_pokemon(team):

    pokemon_names = []
    duplicates = []

    for pokemon in team:
        name = pokemon["name"]
        if name in pokemon_names:
            duplicates.append(name)
        else:
            pokemon_names.append(name)
    return duplicates

def validate_moves(team,pokemon_move_df):

    illegal_moves = []

    for pokemon in team:
        pokemon_name = pokemon["name"]
        legal_moves = pokemon_move_df[
            pokemon_move_df["pokemon"]
            == pokemon_name
        ]["move"].tolist()
        for move in pokemon["moves"]:
            if move not in legal_moves:
                illegal_moves.append({
                    "pokemon": pokemon_name,
                    "move": move
                })

    return illegal_moves

def validate_team(team,pokemon_move_df):

    validation_result = {

        "duplicate_items":
            check_duplicate_items(team),
        "duplicate_pokemon":
            check_duplicate_pokemon(team),
        "illegal_moves":
            validate_moves(
                team,
                pokemon_move_df
            )
    }

    validation_result["valid"] = (
        len(
            validation_result[
                "duplicate_items"
            ]
        ) == 0
        and
        len(
            validation_result[
                "duplicate_pokemon"
            ]
        ) == 0
        and
        len(
            validation_result[
                "illegal_moves"
            ]
        ) == 0
    )

    return validation_result