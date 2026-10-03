import requests
import pandas as pd
import time

BASE_URL = "https://pokeapi.co/api/v2"

item_info = []

# EXTRACT ITEM DATA
def extract_english_effect(effect_entries):
    for effect in effect_entries:
        if effect["language"]["name"] == "en":
            return effect.get("short_effect", "")
    return None

def extract_item(data):
    effect = extract_english_effect(
        data.get("effect_entries", [])
    )
    item_info.append({
        "item_id": data["id"],
        "item_name": data["name"],
        "category": data.get("category", {}).get("name"),
        "effect": effect
    })

# CRAWL ITEM DATA
def crawl_item(start_id=1, end_id=2176):
    for item_id in range(start_id, end_id + 1):
        response = requests.get(
            f"{BASE_URL}/item/{item_id}/"
        )
        if response.status_code == 200:
            data = response.json()
            extract_item(data)
            print(f"SUCCESS {item_id} - {data['name']}")
        else:
            print(f"FAILED ID {item_id}")
        time.sleep(0.3)

crawl_item(1, 2176)

df_items = pd.DataFrame(item_info)

print(df_items.head())

# EXPORT CSV
df_items.to_csv("data/raw/item_raw.csv",index=False)

# EXPORT CSV
df_items.to_csv("data/raw/item_raw.csv",index=False)

# UPLOAD TO SQL
from python.database.db_connection import engine
df_items.to_sql(name="item",con=engine,if_exists="replace",index=False)