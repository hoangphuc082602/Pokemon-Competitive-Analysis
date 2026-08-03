import pandas as pd
from python.database.db_connection import engine


def load_all_pokemon_stats():

    query = """
    SELECT
        p.poke_id,
        p.pokemon,
        MAX(
            CASE
                WHEN pt.slot = 1
                THEN t.type
            END
        ) AS type_1,
        MAX(
            CASE
                WHEN pt.slot = 2
                THEN t.type
            END
        ) AS type_2,
        p.hp,
        p.atk,
        p.def,
        p.spatk,
        p.spdef,
        p.spe
    FROM pokemon_stats p
    LEFT JOIN pokemon_types pt
        ON p.poke_id = pt.pokemon_id
    LEFT JOIN types t
        ON pt.type_id = t.type_id
    GROUP BY
        p.poke_id,
        p.pokemon,
        p.hp,
        p.atk,
        p.def,
        p.spatk,
        p.spdef,
        p.spe
    """
    return pd.read_sql(query, engine)

def get_pokemon_stats(
    pokemon_df,
    pokemon_name
):
    pokemon = pokemon_df[
        pokemon_df["pokemon"] == pokemon_name
    ]
    return pokemon.iloc[0]