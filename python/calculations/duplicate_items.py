def checking_duplicate_items(team):
    items = []
    duplicate_items = []
    for pokemon in team:
        item = pokemon["item"]
        if item in items:
            duplicate_items.append(item)
        else:
            items.append(item)
    return duplicate_items