import pandas as pd
from python.database.db_connection import engine

def load_all_moves():
    query = """
    SELECT
        m.move_name,
        m.power,
        t.type,
        dc.damage_class
    FROM moves m
    JOIN types t
        ON m.type_id = t.type_id
    JOIN damage_classes dc
        ON m.damage_class_id = dc.damage_class_id
    """
    return pd.read_sql(query, engine)

def get_move_data(
    move_df,
    move_name
):
    result = move_df[
        move_df["move_name"] == move_name
    ]
    if result.empty:
        return None

    return result.iloc[0]