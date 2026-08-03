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