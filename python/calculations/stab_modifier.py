def get_stab_modifier(attacker,move):
    if move["type"] in attacker["types"]:
        return 1.5
    return 1