from concurrent.futures import ThreadPoolExecutor
import requests
import pandas as pd

session = requests.Session()

def fetch_pokemon(url):
    try:
        data = session.get(url, timeout=10).json()

        stats = {
            s["stat"]["name"]: s["base_stat"]
            for s in data["stats"]
        }

        species = data["species"]
        species_id = int(
            species["url"]
            .rstrip("/")
            .split("/")[-1]
        )

        return {
            "poke_id": data["id"],
            "pokemon": data["name"],
            "species_id": species_id,
            "hp": stats["hp"],
            "atk": stats["attack"],
            "def": stats["defense"],
            "spatk": stats["special-attack"],
            "spdef": stats["special-defense"],
            "spe": stats["speed"]
        }
    except Exception:
        return None


pokemon_list = requests.get(
    "https://pokeapi.co/api/v2/pokemon?limit=100000"
).json()["results"]

with ThreadPoolExecutor(max_workers=20) as executor:
    results = list(
        executor.map(
            fetch_pokemon,
            [p["url"] for p in pokemon_list]
        )
    )

df = pd.DataFrame([r for r in results if r is not None])

df.to_csv("data/raw/stats_raw.csv", index=False)

# UPLOAD TO SQL database
from python.database.db_connection import engine
df.to_sql(name="pokemon_stats", con=engine, if_exists="replace", index=False)