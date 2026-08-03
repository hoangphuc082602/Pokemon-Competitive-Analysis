import pandas as pd
from python.database.db_connection import engine


def load_all_poke_abi():

    query = """
    SELECT
        p.pokemon,
        a.ability_name,
        pa.hidden_abi
    FROM
        pokemon_abilities pa
    JOIN pokemon_stats p
    ON pa.pokemon_id = p.poke_id
    JOIN ability a
    ON pa.abi_id = a.ability_id
    """
    return pd.read_sql(query, engine)

def get_poke_abi(
    pokemon_df,
    pokemon_name
):
    pokemon = pokemon_df[
        pokemon_df["pokemon"] == pokemon_name
    ]
    return pokemon.iloc[0]