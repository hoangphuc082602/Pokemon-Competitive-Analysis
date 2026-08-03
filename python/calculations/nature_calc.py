STAT_MAPPING = {
    2: "atk",
    3: "def",
    4: "spatk",
    5: "spdef",
    6: "spe"
}

def get_nature_modifiers(nature_df,nature_name):
    modifiers = {
        "atk": 1.0,
        "def": 1.0,
        "spatk": 1.0,
        "spdef": 1.0,
        "spe": 1.0
    }

    nature_row = nature_df[nature_df["nature_name"] == nature_name.lower()]
    if nature_row.empty:
        return modifiers
    increased = nature_row.iloc[0]["increased_stat"]
    decreased = nature_row.iloc[0]["decreased_stat"]
    if increased in STAT_MAPPING:
        modifiers[
            STAT_MAPPING[increased]
        ] = 1.1
    if decreased in STAT_MAPPING:
        modifiers[
            STAT_MAPPING[decreased]
        ] = 0.9

    return modifiers