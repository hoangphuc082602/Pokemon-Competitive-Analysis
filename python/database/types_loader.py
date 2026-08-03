import pandas as pd
from python.database.db_connection import engine

def load_all_types():
    query = """
    SELECT *
    FROM types
    """
    return pd.read_sql(query, engine)

def get_type_data(
    type_df,
    type_name
):

    type_info = type_df[
        type_df["type_name"] == type_name
    ]

    return type_info.iloc[0]