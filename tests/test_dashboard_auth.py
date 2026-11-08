import pytest
from sqlalchemy import text

from app.dashboard_auth import authenticate
from app.db import engine
from app.security import hash_password

PASSWORD = "test-password-123"


@pytest.fixture(scope="module", autouse=True)
def dashboard_user():
    with engine.begin() as conn:
        uid = conn.execute(
            text("INSERT INTO users (username, full_name, password_hash, role) "
                 "VALUES ('test_dash_mgr', 'Test Manager', :h, 'manager') "
                 "ON CONFLICT (username) DO UPDATE SET "
                 "password_hash = EXCLUDED.password_hash RETURNING id"),
            {"h": hash_password(PASSWORD)}).scalar()
        conn.execute(text("DELETE FROM user_businesses WHERE user_id = :i"), {"i": uid})
        conn.execute(
            text("INSERT INTO user_businesses (user_id, business_id) "
                 "SELECT :i, id FROM businesses WHERE code = 'hotels'"), {"i": uid})
    yield uid
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM audit_log WHERE user_id = :i "
                          "OR detail LIKE '%username=test_dash%'"), {"i": uid})
        conn.execute(text("DELETE FROM users WHERE id = :i"), {"i": uid})


def test_correct_login_returns_only_the_users_businesses():
    user = authenticate("test_dash_mgr", PASSWORD)
    assert user["role"] == "manager"
    assert user["businesses"] == ["hotels"]


def test_wrong_password_is_refused():
    assert authenticate("test_dash_mgr", "wrong-password") is None


def test_unknown_user_is_refused():
    assert authenticate("nobody_here", PASSWORD) is None


def test_failed_login_is_audited():
    authenticate("test_dash_mgr", "wrong-password")
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM audit_log WHERE action = 'login_failed' "
                 "AND detail LIKE '%username=test_dash_mgr%'")).scalar()
    assert n >= 1