def get_battle_stats(attacker,defender,move):
    category = move["damage_class"]
    if category == "physical":
        attack_stat = attacker["stats"]["atk"]
        defense_stat = defender["stats"]["def"]
    else:
        attack_stat = attacker["stats"]["spatk"]
        defense_stat = defender["stats"]["spdef"]
    return attack_stat, defense_stat