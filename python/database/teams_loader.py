import pandas as pd
from python.database.db_connection import engine

def load_all_teams():
    query = """
    SELECT *
    FROM team_master
    """

    return pd.read_sql(query,engine)

def get_team(team_df, team_name):
    team = team_df[team_df["team_name"] == team_name]
    return team
