import requests
import pandas as pd
from sqlalchemy import create_engine

BASE_URL = "https://pokeapi.co/api/v2"

damage_class_info = []
def extract_damage_class(data):
    damage_class_id = data["id"]
    damage_class_name = data["name"]

    damage_class_info.append({
        "damage_class_id": damage_class_id,
        "damage_class": damage_class_name
    })

def crawl_damage_classes(start_id=1, end_id=3):
    for dcid in range(start_id, end_id + 1):
        response = requests.get(f"{BASE_URL}/move-damage-class/{dcid}/")
        if response.status_code == 200:
            data = response.json()
            extract_damage_class(data)
            print(f"SUCCESS {dcid} - {data['name']}")
        else:
            print(f"FAILED DAMAGE CLASS {dcid}")

crawl_damage_classes()

df = pd.DataFrame(damage_class_info)
print(df.head())

#EXPORT CSV
df.to_csv("data/raw/data_damage_class.csv",index=False)

# UPLOAD TO SQL
engine = create_engine("mysql+pymysql://root:123456@localhost/pokemon_analytics")
df.to_sql(name="damage_classes",con=engine,if_exists="replace",index=False)
