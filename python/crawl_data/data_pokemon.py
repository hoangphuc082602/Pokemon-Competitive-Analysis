import requests
import pandas as pd

BASE_URL = "https://pokeapi.co/api/v2/pokemon/"

pokemon_master = []

# Extract pokemon data
def extract_pokemon(data):
    types = sorted(data["types"],key=lambda x: x["slot"])

    for t in types:
        type_id = int(
            t["type"]["url"]
            .rstrip("/")
            .split("/")[-1]
        )

        slot = t["slot"]
        pokemon_master.append({
            "pokemon_id": data["id"],
            "type_id": type_id,
            "slot": slot
        })

# Crawl data from pokeapi
def crawl_pokemon(start_id=1, end_id=1025):
    
    for pid in range(start_id, end_id + 1):
        response = requests.get(f"{BASE_URL}{pid}")

        if response.status_code == 200:
            data = response.json()
            extract_pokemon(data)
            print(f"SUCCESS {pid} - {data['name']}")
        else:
            print(f"Failed ID {pid}")

crawl_pokemon(1, 1025)
# Create DataFrame
df = pd.DataFrame(pokemon_master)
print(df)

# Save csv
df.to_csv("data/raw/pokemon_type_raw.csv",index=False)

# Upload to SQL
from python.database.db_connection import engine
df.to_sql(name="pokemon_types",con=engine,if_exists="replace",index=False)