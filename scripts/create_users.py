"""Create (or reset) the three pilot users. Passwords are typed in, never stored
in the code."""
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from app.security import hash_password

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))

USERS = [
    ("vishnu", "Vishnu", "manager", ["hotels"]),
    ("meghana", "Meghana", "planner", ["railway", "hotels", "park"]),
    ("dhiren", "Dhiren", "admin", ["railway", "hotels", "park"]),
]

for username, full_name, role, codes in USERS:
    while True:
        password = getpass.getpass(f"Password for {username} ({role}): ")
        if len(password) >= 8:
            break
        print("  Use at least 8 characters.")
    with engine.begin() as conn:
        user_id = conn.execute(
            text("INSERT INTO users (username, full_name, password_hash, role) "
                 "VALUES (:u, :n, :h, :r) ON CONFLICT (username) DO UPDATE SET "
                 "full_name = EXCLUDED.full_name, "
                 "password_hash = EXCLUDED.password_hash, role = EXCLUDED.role "
                 "RETURNING id"),
            {"u": username, "n": full_name, "h": hash_password(password), "r": role},
        ).scalar()
        conn.execute(text("DELETE FROM user_businesses WHERE user_id = :i"),
                     {"i": user_id})
        for code in codes:
            conn.execute(
                text("INSERT INTO user_businesses (user_id, business_id) "
                     "SELECT :i, id FROM businesses WHERE code = :c"),
                {"i": user_id, "c": code})
    print(f"  {username}: {role}, access to {', '.join(codes)}")