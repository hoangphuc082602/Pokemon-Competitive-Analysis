from sqlalchemy import text
from .db_connection import engine

with engine.connect() as conn:
    conn.execute(text("SELECT 1"))

print("Connected successfully!")