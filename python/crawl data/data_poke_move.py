import requests
import pandas as pd
import time
from sqlalchemy import create_engine

BASE_URL = "https://pokeapi.co/api/v2"
LATEST_VERSION = "scarlet-violet"

pokemon_moves = []

# EXTRACT MOVE DATA
def extract_moves(data):
    pokemon_id = data["id"]
    for move in data["moves"]:
        move_id = int(
            move["move"]["url"]
            .rstrip("/")
            .split("/")[-1]
        )
        for detail in move["version_group_details"]:
            if(detail["version_group"]["name"] != LATEST_VERSION):
                continue
            learn_method = detail["move_learn_method"]
            learn_method_id = int(
                learn_method["url"]
                .rstrip("/")
                .split("/")[-1]
            )

            pokemon_moves.append({
                "pokemon_id": pokemon_id,
                "move_id": move_id,
                "learn_method": learn_method_id,
                "level_learned":
                    detail["level_learned_at"]
            })

# CRAWL DATA
def crawl_moves(start_id=1, end_id=1025):
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
crawl_moves(1, 1025)

# DATAFRAME
df_moves = pd.DataFrame(pokemon_moves)
print(df_moves.head())

# EXPORT CSV
df_moves.to_csv("data/raw/pokemon_moves.csv",index=False)

# UPLOAD TO SQL
engine = create_engine("mysql+pymysql://root:123456@localhost/pokemon_analytics")
df_moves.to_sql(name="pokemon_moves",con=engine,if_exists="replace",index=False)