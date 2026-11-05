import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))

sql = Path(__file__).with_name("schema.sql").read_text()

with engine.begin() as conn:
    conn.exec_driver_sql(sql)

print("Tables created.")