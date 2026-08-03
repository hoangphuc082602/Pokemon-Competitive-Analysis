import requests
import pandas as pd
import time
from sqlalchemy import create_engine

BASE_URL = "https://pokeapi.co/api/v2"

evolution_data = []

# EXTRACT EVO METHOD ID
def get_method_id(method_data):
    if not method_data:
        return None
    return int(
        method_data["url"]
        .rstrip("/")
        .split("/")[-1]
    )

# RECURSIVE EVOLUTION PARSER
def parse_chain(chain, prev_id=None):
    current_id = int(
        chain["species"]["url"]
        .rstrip("/")
        .split("/")[-1]
    )
    evolves_to = chain["evolves_to"]

    for evo in evolves_to:
        next_id = int(
            evo["species"]["url"]
            .rstrip("/")
            .split("/")[-1]
        )
        details = evo["evolution_details"]
        evo_method_id = None
        evo_level = None

        if details:
            detail = details[0]
            evo_method_id = get_method_id(
                detail.get("trigger")
            )
            evo_level = detail.get(
                "min_level"
            )

        evolution_data.append({
            "pokemon_id": current_id,
            "prev_id": prev_id,
            "next_id": next_id,
            "evo_method_id": evo_method_id,
            "evo_level": evo_level
        })

        # RECURSIVE
        parse_chain(evo, current_id)

# CRAWL EVOLUTION CHAINS
def crawl_evolution_chains(start_id=1, end_id=1025):
    visited_chains = set()
    for pokemon_id in range(start_id, end_id + 1):
        species_response = requests.get(
            f"{BASE_URL}/pokemon-species/{pokemon_id}/"
        )
        if species_response.status_code != 200:
            print(f"FAILED SPECIES {pokemon_id}")
            continue
        species_data = species_response.json()
        chain_url = species_data[
            "evolution_chain"
        ]["url"]

        chain_id = int(
            chain_url.rstrip("/")
            .split("/")[-1]
        )

        # AVOID DUPLICATE CHAINS
        if chain_id in visited_chains:
            continue
        visited_chains.add(chain_id)
        chain_response = requests.get(chain_url)
        if chain_response.status_code == 200:
            chain_data = chain_response.json()
            parse_chain(chain_data["chain"])
            print(f"SUCCESS CHAIN {chain_id}")
        else:
            print(f"FAILED CHAIN {chain_id}")
        time.sleep(0.3)

crawl_evolution_chains()

# DATAFRAME
df = pd.DataFrame(evolution_data).drop_duplicates()

print(df.head())

# EXPORT CSV
df.to_csv("data/raw/evolution_raw.csv",index=False)

# UPLOAD TO MYSQL
engine = create_engine("mysql+pymysql://root:123456@localhost/pokemon_analytics")
df.to_sql(name="pokemon_evolution",con=engine,if_exists="replace",index=False)