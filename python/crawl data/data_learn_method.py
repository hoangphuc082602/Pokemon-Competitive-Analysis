import requests
import pandas as pd
import time
from sqlalchemy import create_engine

BASE_URL = "https://pokeapi.co/api/v2"

learn_method_info = []

# EXTRACT LEARN METHOD DATA
def extract_learn_method(data):
    learn_method_info.append({
        "learn_method_id": data["id"],
        "learn_method": data["name"]
    })

# CRAWL MOVE DATA
def crawl_abi(start_id=1, end_id=11):
    for learn_method_id in range(start_id, end_id + 1):
        response = requests.get(
            f"{BASE_URL}/move-learn-method/{learn_method_id}/"
        )
        if response.status_code == 200:
            data = response.json()
            extract_learn_method(data)
            print(f"SUCCESS {learn_method_id} - {data['name']}")
        else:
            print(f"FAILED ID {learn_method_id}")
        time.sleep(0.3)

crawl_abi(1, 11)

df_abilities = pd.DataFrame(learn_method_info)

print(df_abilities.head())

# EXPORT CSV
df_abilities.to_csv("data/raw/learn_method_raw.csv",index=False)

# UPLOAD TO SQL
engine = create_engine("mysql+pymysql://root:123456@localhost/pokemon_analytics")
df_abilities.to_sql(name="learn_method",con=engine,if_exists="replace",index=False)