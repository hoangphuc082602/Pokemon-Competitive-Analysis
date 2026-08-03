def calculate_ohko_chance(
    min_damage,
    max_damage,
    defender_hp
):
    damage_rolls = []
    for i in range(85, 101):
        modifier = i / 100
        damage = int(
            max_damage * modifier
        )
        damage_rolls.append(damage)
    kill_rolls = sum(
        dmg >= defender_hp
        for dmg in damage_rolls
    )
    return (
        kill_rolls / 16
    ) * 100

def calculate_2hko_chance(
    min_damage,
    max_damage,
    defender_hp
):
    damage_rolls = []
    for i in range(85, 101):
        modifier = i / 100
        damage = int(
            max_damage * modifier
        )
        damage_rolls.append(damage)
    kill_rolls = sum(
        dmg >= (defender_hp / 2)
        for dmg in damage_rolls
    )
    return (
        kill_rolls / 16
    ) * 100