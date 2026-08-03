import pandas as pd
from python.database.db_connection import engine

def load_type_effectiveness():
    query = """
    SELECT
        atk.type AS attack_type,
        def.type AS defense_type,
        te.multiplier
    FROM type_effectiveness te
    JOIN types atk
        ON te.attack_type_id = atk.type_id
    JOIN types def
        ON te.defense_type_id = def.type_id
    """
    return pd.read_sql(query, engine)

def get_type_effectiveness(
    type_effectiveness_df,
    attacking_type,
    defending_type
):

    effectiveness = type_effectiveness_df[
        (type_effectiveness_df["attacking_type"] == attacking_type) &
        (type_effectiveness_df["defending_type"] == defending_type)
    ]

    return effectiveness.iloc[0]