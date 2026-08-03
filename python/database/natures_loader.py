import pandas as pd
from python.database.db_connection import engine

def load_all_natures():
    query = """
    SELECT *
    FROM nature
    """
    return pd.read_sql(query, engine)

def get_nature_data(
    nature_df,
    nature_name
):

    nature = nature_df[
        nature_df["nature"] == nature_name
    ]

    return nature.iloc[0]
