import requests
import pandas as pd

BASE_URL = "https://pokeapi.co/api/v2"

nature_info = []
def extract_nature_info(data):
    nature_id = data["id"]
    nature_name = data["name"]
    decreased_stat = data["decreased_stat"]
    if decreased_stat:
        decreased_stat = int(
                decreased_stat["url"]
                .rstrip("/")
                .split("/")[-1]
            )
    else:
        decreased_stat = None
    increased_stat = data["increased_stat"]
    if increased_stat:
        increased_stat = int(
                increased_stat["url"]
                .rstrip("/")
                .split("/")[-1]
            )
    else:
        increased_stat = None
    nature_info.append({
        "nature_id": nature_id,
        "nature_name": nature_name,
        "decreased_stat": decreased_stat,
        "increased_stat": increased_stat
    })

def crawl_nature_info(start_id=1, end_id=25):
    for nature_id in range(start_id, end_id + 1):
        response = requests.get(
            f"{BASE_URL}/nature/{nature_id}/"
        )
        if response.status_code == 200:
            data = response.json()
            extract_nature_info(data)
            print(
                f"SUCCESS {nature_id} - {data['name']}"
            )
        else:
            print(f"FAILED ID {nature_id}")

crawl_nature_info(1, 25)

# DATAFRAME
df_nature_info = pd.DataFrame(nature_info)
print(df_nature_info.head())

# EXPORT CSV
df_nature_info.to_csv("data/raw/pokemon_nature_info.csv",index=False)

# UPLOAD TO SQL
from python.database.db_connection import engine
df_nature_info.to_sql(name="nature",con=engine,if_exists="replace",index=False)