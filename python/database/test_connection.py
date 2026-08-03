from sqlalchemy import create_engine

username = "root"
password = "123456"

host = "localhost"
database = "pokemon_analytics"

engine = create_engine(
    f"mysql+pymysql://{username}:{password}@{host}/{database}"
)

print("Connected successfully!")