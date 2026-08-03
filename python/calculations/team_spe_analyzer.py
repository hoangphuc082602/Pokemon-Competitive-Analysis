from python.calculations.speed_calc import (
    calculate_speed
)

def analyze_team_speed(
    team
):
    speeds = []
    for pokemon in team:
        name = pokemon["name"]
        base_speed = pokemon["base_speed"]
        iv = pokemon["ivs"]["spe"]
        ev = pokemon["evs"]["spe"]
        level = pokemon["level"]
        nature_modifier = pokemon["nature_modifier_speed"]
        item_name = pokemon.get("item_name", None)

        speeds.append(calculate_speed(
            base_speed,
            iv,
            ev,
            level,
            nature_modifier,
            item_name
        ))
    avg_speed = sum(speeds) / len(speeds)
    fast_count = len([s for s in speeds if s >= 115])

    return {
        "average_speed": round(avg_speed, 2),
        "fast_pokemon_count": fast_count
    }
