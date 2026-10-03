import requests
import pandas as pd
import time


BASE_URL = "https://pokeapi.co/api/v2"

type_effectiveness = []

# EXTRACT TYPE EFFECTIVENESS
def extract_type_effectiveness(data):
    attack_type_id = data["id"]
    damage_relations = data["damage_relations"]
    relation_map = {
        "double_damage_to": 2.0,
        "half_damage_to": 0.5,
        "no_damage_to": 0.0
    }

    for relation_name, multiplier in relation_map.items():
        for defense_type in damage_relations[relation_name]:
            defense_type_id = int(
                defense_type["url"]
                .rstrip("/")
                .split("/")[-1]
            )

            type_effectiveness.append({
                "attack_type_id": attack_type_id,
                "defense_type_id": defense_type_id,
                "multiplier": multiplier
            })

# CRAWL TYPE DATA
def crawl_types(start_id=1, end_id=19):
    for type_id in range(start_id, end_id + 1):
        response = requests.get(f"{BASE_URL}/type/{type_id}/")
        if response.status_code == 200:
            data = response.json()
            extract_type_effectiveness(data)
            print(f"SUCCESS {type_id} - {data['name']}")
        else:
            print(f"FAILED TYPE {type_id}")
        time.sleep(0.2)

crawl_types()

# DATAFRAME
df = pd.DataFrame(type_effectiveness)

print(df.head())

# EXPORT CSV
df.to_csv("data/raw/type_effectiveness.csv",index=False)

# UPLOAD TO SQL
from python.database.db_connection import engine
df.to_sql(name="type_effectiveness",con=engine,if_exists="replace",index=False)