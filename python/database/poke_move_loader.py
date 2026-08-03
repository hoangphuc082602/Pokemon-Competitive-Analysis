import pandas as pd
from python.database.db_connection import engine


def load_all_pokemon_moves():

    query = """
    SELECT
        p.pokemon,
        m.move_name,
        lm.learn_method,
        pm.level_learned
    FROM pokemon_moves pm
    JOIN pokemon_stats p
    ON pm.pokemon_id = p.poke_id
    JOIN moves m
    ON pm.move_id = m.move_id
    JOIN learn_method lm
    ON pm.learn_method = lm.learn_method_id
    """
    return pd.read_sql(query, engine)

def get_pokemon_moves(
    pokemon_df,
    pokemon_name
):
    pokemon = pokemon_df[
        pokemon_df["pokemon"] == pokemon_name
    ]
    return pokemon.iloc[0]