import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import engine
from app.main import app
from app.security import hash_password

client = TestClient(app)
PASSWORD = "test-password-123"
RANGE = {"start": "2026-10-01", "end": "2026-10-07"}


@pytest.fixture(scope="module", autouse=True)
def test_users():
    specs = [("test_hotel_mgr", "manager", ["hotels"]),
             ("test_admin", "admin", ["railway", "hotels", "park"])]
    ids = []
    with engine.begin() as conn:
        for username, role, codes in specs:
            uid = conn.execute(
                text("INSERT INTO users (username, full_name, password_hash, role) "
                     "VALUES (:u, :u, :h, :r) ON CONFLICT (username) DO UPDATE SET "
                     "password_hash = EXCLUDED.password_hash, role = EXCLUDED.role "
                     "RETURNING id"),
                {"u": username, "h": hash_password(PASSWORD), "r": role}).scalar()
            ids.append(uid)
            conn.execute(text("DELETE FROM user_businesses WHERE user_id = :i"),
                         {"i": uid})
            for code in codes:
                conn.execute(
                    text("INSERT INTO user_businesses (user_id, business_id) "
                         "SELECT :i, id FROM businesses WHERE code = :c"),
                    {"i": uid, "c": code})
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM audit_log WHERE user_id = ANY(:ids) "
                          "OR detail LIKE 'username=test_%'"), {"ids": ids})
        conn.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": ids})


def auth(username):
    r = client.post("/login", data={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_wrong_password_is_rejected():
    r = client.post("/login", data={"username": "test_admin", "password": "nope"})
    assert r.status_code == 401


def test_data_requires_login():
    assert client.get("/businesses/hotels/daily", params=RANGE).status_code == 401


def test_hotel_manager_can_see_hotels():
    r = client.get("/businesses/hotels/daily", params=RANGE,
                   headers=auth("test_hotel_mgr"))
    assert r.status_code == 200
    assert len(r.json()["data"]) == 7


def test_hotel_manager_cannot_see_railway():
    r = client.get("/businesses/railway/daily", params=RANGE,
                   headers=auth("test_hotel_mgr"))
    assert r.status_code == 403


def test_manager_cannot_read_audit_log():
    assert client.get("/audit-log", headers=auth("test_hotel_mgr")).status_code == 403


def test_admin_can_read_audit_log():
    assert client.get("/audit-log", headers=auth("test_admin")).status_code == 200


def test_refused_request_is_audited():
    client.get("/businesses/railway/daily", params=RANGE,
               headers=auth("test_hotel_mgr"))
    log = client.get("/audit-log", headers=auth("test_admin")).json()
    assert any(e["action"] == "access_denied" and e["user"] == "test_hotel_mgr"
               for e in log)