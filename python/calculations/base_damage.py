def calc_base_damage (attacker, move, attack_stat, defense_stat):
    level = attacker["level"]
    power = move["power"]
    base_damage = (
        (
            (
                (
                    (
                        2
                        * level
                    ) / 5
                ) + 2
            )
            * power
            * attack_stat
            / defense_stat
        ) / 50
    ) + 2
    return base_damage