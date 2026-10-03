import pandas as pd
from sqlalchemy import create_engine
import requests
import time

BASE_URL = "https://pokeapi.co/api/v2"

pokemon_species = []

# EXTRACT SPECIES DATA
def extract_species(data):
    pokemon_species.append({
        "species_id": data["id"],
        "species": data["name"],
        "is_legendary": data["is_legendary"],
        "is_mythical": data["is_mythical"]
    })

# CRAWL DATA
def crawl_species(start_id=1, end_id=1025):
    for species_id in range(start_id, end_id + 1):
        response = requests.get(
            f"{BASE_URL}/pokemon-species/{species_id}/"
        )
        if response.status_code == 200:
            data = response.json()
            extract_species(data)
            print(
                f"SUCCESS {species_id} - {data['name']}"
            )
        else:
            print(f"FAILED ID {species_id}")
        time.sleep(0.3)
crawl_species(1, 1025)

# DATAFRAME
df_species = pd.DataFrame(pokemon_species)
print(df_species.head())

# EXPORT CSV
df_species.to_csv("data/raw/pokemon_species.csv",index=False)

# UPLOAD TO SQL
engine = create_engine("mysql+pymysql://root:123456@localhost/pokemon_analytics")
df_species.to_sql(name="pokemon_species",con=engine,if_exists="replace",index=False)
