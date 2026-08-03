import requests
import pandas as pd
import time
from sqlalchemy import create_engine

BASE_URL = "https://pokeapi.co/api/v2"

move_info = []

# EXTRACT MOVE DATA
def extract_english_effect(effect_entries):
    for effect in effect_entries:
        if effect["language"]["name"] == "en":
            return effect.get("short_effect", "")
    return None

def extract_move(data):
    effect = extract_english_effect(
        data.get("effect_entries", [])
    )

    type_move = data.get("type", {})
    damage_class = data.get("damage_class", {})
    type_id = int(
        type_move["url"]
        .rstrip("/")
        .split("/")[-1]
    )
    class_id = int(
        damage_class["url"]
        .rstrip("/")
        .split("/")[-1]
    )
    move_info.append({
        "move_id": data["id"],
        "move_name": data["name"],
        "type_id": type_id,
        "damage_class_id": class_id,
        "accuracy": data.get("accuracy"),
        "pp": data.get("pp"),
        "power": data.get("power"),
        "priority": data.get("priority"),
        "effect": effect
    })

# CRAWL MOVE DATA
def crawl_moves(start_id=1, end_id=920):
    for move_id in range(start_id, end_id + 1):
        response = requests.get(
            f"{BASE_URL}/move/{move_id}/"
        )
        if response.status_code == 200:
            data = response.json()
            extract_move(data)
            print(f"SUCCESS {move_id} - {data['name']}")
        else:
            print(f"FAILED ID {move_id}")
        time.sleep(0.3)

crawl_moves(1, 920)

df_moves = pd.DataFrame(move_info)

print(df_moves.head())

# EXPORT CSV
df_moves.to_csv("data/raw/move_raw.csv",index=False)

# UPLOAD TO SQL
engine = create_engine("mysql+pymysql://root:123456@localhost/pokemon_analytics")
df_moves.to_sql(name="moves",con=engine,if_exists="replace",index=False)