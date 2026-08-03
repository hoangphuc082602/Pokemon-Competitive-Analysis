import requests
import pandas as pd
import time

from sqlalchemy import create_engine

BASE_URL = "https://pokeapi.co/api/v2"

type_info = []

#EXTRACT TYPE DATA
def extract_type(data):
    typeid = data["id"]
    type = data["name"]
    type_info.append({
        "type_id": typeid,
        "type": type
    })

#CRAWL DATA TYPES
def crawl_types(start_id=1, end_id=19):
    for tid in range(start_id, end_id + 1):
        response = requests.get(f"{BASE_URL}/type/{tid}/")
        if response.status_code == 200:
            data = response.json()
            extract_type(data)
            print(f"SUCCESS {tid} - {data['name']}")
        else:
            print(f"FAILED TYPE {tid}")
        time.sleep(0.2)

crawl_types()

#DATAFRAME
df = pd.DataFrame(type_info)
print(df.head())

#EXPORT CSV
df.to_csv("data/raw/data_type.csv",index=False)

# UPLOAD TO SQL
engine = create_engine("mysql+pymysql://root:123456@localhost/pokemon_analytics")
df.to_sql(name="types",con=engine,if_exists="replace",index=False)