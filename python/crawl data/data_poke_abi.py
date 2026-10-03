import requests
import pandas as pd
import time
from sqlalchemy import create_engine

BASE_URL = "https://pokeapi.co/api/v2"

pokemon_abilities = []

# EXTRACT MOVE DATA
def extract_moves(data):
    pokemon_id = data["id"]
    for abi in data["abilities"]:
        abi_id = int(
            abi["ability"]["url"]
            .rstrip("/")
            .split("/")[-1])
        hidden = abi["is_hidden"]

        pokemon_abilities.append({
            "pokemon_id": pokemon_id,
            "abi_id": abi_id,
            "hidden_abi": hidden
        })

# CRAWL DATA
def crawl_pokemon_abilities(start_id=1, end_id=1025):
    for poke_id in range(start_id, end_id + 1):
        response = requests.get(
            f"{BASE_URL}/pokemon/{poke_id}/"
        )
        if response.status_code == 200:
            data = response.json()
            extract_moves(data)
            print(
                f"SUCCESS {poke_id} - {data['name']}"
            )
        else:
            print(f"FAILED ID {poke_id}")
        time.sleep(0.3)
crawl_pokemon_abilities(1, 1025)

# DATAFRAME
df_poke_abilities = pd.DataFrame(pokemon_abilities)
print(df_poke_abilities.head())

# EXPORT CSV
df_poke_abilities.to_csv("data/raw/pokemon_ability.csv",index=False)

# UPLOAD TO SQL
engine = create_engine("mysql+pymysql://root:123456@localhost/pokemon_analytics")
df_poke_abilities.to_sql(name="pokemon_abilities",con=engine,if_exists="replace",index=False)