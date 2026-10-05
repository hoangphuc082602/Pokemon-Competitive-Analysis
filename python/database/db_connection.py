import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

# .env nằm ở thư mục gốc repo
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DB_URL = URL.create(
    drivername="mysql+pymysql",
    username=os.getenv("DB_USER", "root"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "3306")),
    database=os.getenv("DB_NAME", "pokemon_analytics"),
)

engine = create_engine(DB_URL, pool_pre_ping=True)