def label_role(pokemon):
    stats = pokemon["stats"]
    atk = stats["atk"]
    spatk = stats["spatk"]
    defense = stats["def"]
    spdef = stats["spdef"]
    speed = stats["spe"]

    # PHYSICAL SWEEPER
    if atk >= 170 and speed >= 150:
        return "physical_sweeper"

    # SPECIAL SWEEPER
    if spatk >= 170 and speed >= 150:
        return "special_sweeper"

    # WALL
    if defense >= 150 or spdef >= 150:
        return "wall"
    return "balanced"