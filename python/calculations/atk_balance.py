def analyze_damage_profile(
    team,
    move_df
):

    physical_count = 0
    special_count = 0

    for pokemon in team:

        for move_name in pokemon["moves"]:
            move_data = move_df[
                move_df["move_name"] == move_name
            ]
            if move_data.empty:
                continue
            category = (
                move_data.iloc[0]["damage_class"]
            )
            if category == "physical":
                physical_count += 1
            elif category == "special":
                special_count += 1

    return {
        "physical_moves": physical_count,
        "special_moves": special_count
    }