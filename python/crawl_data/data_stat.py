import requests
import pandas as pd

BASE_URL = "https://pokeapi.co/api/v2"

stat_info = []
def extract_stat_info(data):
    stat_id = data["id"]
    stat_name = data["name"]
    stat_info.append({
        "stat_id": stat_id,
        "stat_name": stat_name
    })
def crawl_stat_info(start_id=1, end_id=10):
    for stat_id in range(start_id, end_id + 1):
        response = requests.get(
            f"{BASE_URL}/stat/{stat_id}/"
        )
        if response.status_code == 200:
            data = response.json()
            extract_stat_info(data)
            print(
                f"SUCCESS {stat_id} - {data['name']}"
            )
        else:
            print(f"FAILED ID {stat_id}")
crawl_stat_info(1, 10)

# DATAFRAME
df_stat_info = pd.DataFrame(stat_info)
print(df_stat_info.head())

# EXPORT CSV
df_stat_info.to_csv("data/raw/stat_info.csv",index=False)

# UPLOAD TO SQL
from python.database.db_connection import engine
df_stat_info.to_sql(name="stat_info",con=engine,if_exists="replace",index=False)