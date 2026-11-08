from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import assistant
from app.db import engine
from app.main import app
from app.security import hash_password

client = TestClient(app)
LATEST = date(2026, 10, 31)
PASSWORD = "test-password-123"


def test_last_month_is_the_latest_full_month():
    start, end, _ = assistant.parse_period(
        "which day last month had the lowest occupancy", LATEST)
    assert (start, end) == (date(2026, 10, 1), date(2026, 10, 31))


def test_last_month_with_partial_data_uses_previous_month():
    start, end, _ = assistant.parse_period("last month", date(2026, 11, 7))
    assert (start, end) == (date(2026, 10, 1), date(2026, 10, 31))


def test_single_date_is_understood():
    start, end, _ = assistant.parse_period(
        "why did ridership fall on 18 september 2025", LATEST)
    assert start == end == date(2025, 9, 18)


def test_year_is_understood():
    start, end, _ = assistant.parse_period("show unusual days in 2025", LATEST)
    assert (start, end) == (date(2025, 1, 1), date(2025, 12, 31))


def test_business_is_detected():
    assert assistant.detect_business("which hotel had the lowest occupancy") == "hotels"
    assert assistant.detect_business("how many passengers last week") == "railway"
    assert assistant.detect_business("show park visitors") == "park"


def test_intent_is_detected():
    assert assistant.detect_intent("why did it drop") == "why"
    assert assistant.detect_intent("which day had the lowest occupancy") == "lowest"
    assert assistant.detect_intent("almost nothing") is None


@pytest.fixture(scope="module")
def manager():
    with engine.begin() as conn:
        uid = conn.execute(
            text("INSERT INTO users (username, full_name, password_hash, role) "
                 "VALUES ('test_ask_mgr', 'test', :h, 'manager') "
                 "ON CONFLICT (username) DO UPDATE SET password_hash = "
                 "EXCLUDED.password_hash RETURNING id"),
            {"h": hash_password(PASSWORD)}).scalar()
        conn.execute(text("DELETE FROM user_businesses WHERE user_id = :i"), {"i": uid})
        conn.execute(
            text("INSERT INTO user_businesses (user_id, business_id) "
                 "SELECT :i, id FROM businesses WHERE code = 'hotels'"), {"i": uid})
    r = client.post("/login", data={"username": "test_ask_mgr", "password": PASSWORD})
    yield uid, {"Authorization": f"Bearer {r.json()['access_token']}"}
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM audit_log WHERE user_id = :i OR "
                          "detail LIKE 'username=test_ask%'"), {"i": uid})
        conn.execute(text("DELETE FROM users WHERE id = :i"), {"i": uid})


def test_manager_gets_an_answer_about_hotels(manager):
    _, headers = manager
    r = client.post("/ask", headers=headers,
                    json={"question": "Which day last month had the lowest occupancy?"})
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "October 2026" in r.json()["answer"]


def test_manager_cannot_ask_about_railway(manager):
    _, headers = manager
    r = client.post("/ask", headers=headers,
                    json={"question": "What was the average ridership in 2025?"})
    assert r.status_code == 403


def test_typhoon_day_is_explained_from_the_data(manager):
    _, headers = manager
    r = client.post("/ask", headers=headers, json={
        "question": "Why did occupancy drop on 18 September 2025?"})
    answer = r.json()["answer"]
    assert "210 mm" in answer
    assert "flagged this day as unusual" in answer


def test_questions_are_audited(manager):
    uid, headers = manager
    client.post("/ask", headers=headers,
                json={"question": "What is the forecast for hotels next week?"})
    with engine.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM audit_log WHERE user_id = :i "
                              "AND action = 'question'"), {"i": uid}).scalar()
    assert n >= 1