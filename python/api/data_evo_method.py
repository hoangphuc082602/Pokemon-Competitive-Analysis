import requests
import pandas as pd
from sqlalchemy import create_engine

BASE_URL = "https://pokeapi.co/api/v2"

evo_method_info = []
def extract_evo_method(data):
    evo_method_id = data["id"]
    evo_method_name = data["name"]

    evo_method_info.append({
        "evo_method_id": evo_method_id,
        "evo_method": evo_method_name
    })
def crawl_evo_methods(start_id=1, end_id=16):
    for emid in range(start_id, end_id + 1):
        response = requests.get(f"{BASE_URL}/evolution-trigger/{emid}/")
        if response.status_code == 200:
            data = response.json()
            extract_evo_method(data)
            print(f"SUCCESS {emid} - {data['name']}")
        else:
            print(f"FAILED EVO METHOD {emid}")

crawl_evo_methods()

df = pd.DataFrame(evo_method_info)
print(df.head())

#EXPORT CSV
df.to_csv("data/raw/data_evo_method.csv",index=False)

# UPLOAD TO SQL
engine = create_engine("mysql+pymysql://root:123456@localhost/pokemon_analytics")
df.to_sql(name="evo_methods",con=engine,if_exists="replace",index=False)
