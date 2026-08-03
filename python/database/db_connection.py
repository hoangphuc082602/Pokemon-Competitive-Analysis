from sqlalchemy import create_engine

USERNAME = "root"
PASSWORD = "123456"

HOST = "localhost"
DATABASE = "pokemon_analytics"

engine = create_engine(
    f"mysql+pymysql://{USERNAME}:{PASSWORD}@{HOST}/{DATABASE}"
)