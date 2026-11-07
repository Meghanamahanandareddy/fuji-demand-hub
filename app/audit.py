from sqlalchemy import text

from app.db import engine


def write(user_id, action, detail=None):
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO audit_log (user_id, action, detail) "
                 "VALUES (:u, :a, :d)"),
            {"u": user_id, "a": action, "d": detail},
        )