import pandas as pd
from python.database.db_connection import engine

def load_all_items():
    query = """
    SELECT *
    FROM item
    """
    return pd.read_sql(query, engine)