"""Login for the dashboard, using the same users table and password hashing as the
API. Every login, failed login and logout is written to the audit log."""
from sqlalchemy import text

from app import audit, security
from app.db import engine


def authenticate(username, password):
    """Return the user (with the businesses they may see), or None."""
    username = username.strip()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, username, full_name, role, password_hash "
                 "FROM users WHERE username = :u"),
            {"u": username}).mappings().first()
    if row is None or not security.verify_password(password, row["password_hash"]):
        audit.write(None, "login_failed", f"dashboard username={username[:50]}")
        return None
    with engine.connect() as conn:
        codes = [r[0] for r in conn.execute(
            text("SELECT b.code FROM user_businesses ub "
                 "JOIN businesses b ON b.id = ub.business_id "
                 "WHERE ub.user_id = :i ORDER BY b.code"), {"i": row["id"]})]
    audit.write(row["id"], "dashboard_login")
    return {"id": row["id"], "username": row["username"],
            "full_name": row["full_name"], "role": row["role"],
            "businesses": codes}


def logout(user_id):
    audit.write(user_id, "dashboard_logout")