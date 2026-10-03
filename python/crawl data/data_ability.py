import requests
import pandas as pd
import time
from sqlalchemy import create_engine

BASE_URL = "https://pokeapi.co/api/v2"

ability_info = []

# EXTRACT MOVE DATA
def extract_english_effect(effect_entries):
    for effect in effect_entries:
        if effect["language"]["name"] == "en":
            return effect.get("short_effect", "")
    return None

def extract_abi(data):
    effect = extract_english_effect(
        data.get("effect_entries", [])
    )
    ability_info.append({
        "ability_id": data["id"],
        "ability_name": data["name"],
        "effect": effect
    })

# CRAWL MOVE DATA
def crawl_abi(start_id=1, end_id=371):
    for ability_id in range(start_id, end_id + 1):
        response = requests.get(
            f"{BASE_URL}/ability/{ability_id}/"
        )
        if response.status_code == 200:
            data = response.json()
            extract_abi(data)
            print(f"SUCCESS {ability_id} - {data['name']}")
        else:
            print(f"FAILED ID {ability_id}")
        time.sleep(0.3)

crawl_abi(1, 371)

df_abilities = pd.DataFrame(ability_info)

print(df_abilities.head())

# EXPORT CSV
df_abilities.to_csv("data/raw/ability_raw.csv",index=False)

# UPLOAD TO SQL
engine = create_engine("mysql+pymysql://root:123456@localhost/pokemon_analytics")
df_abilities.to_sql(name="ability",con=engine,if_exists="replace",index=False)