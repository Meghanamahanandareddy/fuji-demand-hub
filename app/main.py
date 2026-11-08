"""REST API: login, role-based access to business data, forecasts, questions,
audit log."""
from datetime import date

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import text

from app import assistant, audit, security
from app.db import engine

app = FastAPI(title="Mt. Fuji Tourism Demand Hub API")
oauth2 = OAuth2PasswordBearer(tokenUrl="login")

METRIC = {"railway": "passengers", "hotels": "occupancy_pct", "park": "visitors"}
DAILY_SQL = {
    "railway": "SELECT date, sum(passengers)::float AS value FROM ridership_daily "
               "WHERE date BETWEEN :s AND :e GROUP BY date ORDER BY date",
    "hotels": "SELECT date, round(sum(rooms_booked)::numeric / "
              "sum(rooms_available) * 100, 1)::float AS value FROM hotel_daily "
              "WHERE date BETWEEN :s AND :e GROUP BY date ORDER BY date",
    "park": "SELECT date, visitors::float AS value FROM park_daily "
            "WHERE date BETWEEN :s AND :e ORDER BY date",
}


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=300)


def get_user(token: str = Depends(oauth2)):
    user_id = security.read_token(token)
    unauthorized = HTTPException(
        401, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    if user_id is None:
        raise unauthorized
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, username, full_name, role FROM users WHERE id = :i"),
            {"i": user_id}).mappings().first()
        if row is None:
            raise unauthorized
        codes = [r[0] for r in conn.execute(
            text("SELECT b.code FROM user_businesses ub "
                 "JOIN businesses b ON b.id = ub.business_id "
                 "WHERE ub.user_id = :i ORDER BY b.code"), {"i": user_id})]
    return {**dict(row), "businesses": codes}


def require_business(user, code):
    if code not in METRIC:
        raise HTTPException(404, "Unknown business")
    if code not in user["businesses"]:
        audit.write(user["id"], "access_denied", f"business={code}")
        raise HTTPException(403, "You do not have access to this business")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends()):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, password_hash FROM users WHERE username = :u"),
            {"u": form.username}).first()
    if row is None or not security.verify_password(form.password, row.password_hash):
        audit.write(None, "login_failed", f"username={form.username}")
        raise HTTPException(401, "Wrong username or password")
    audit.write(row.id, "login")
    return {"access_token": security.create_token(row.id), "token_type": "bearer"}


@app.get("/me")
def me(user=Depends(get_user)):
    return user


@app.get("/businesses/{code}/daily")
def daily(code: str, start: date, end: date, user=Depends(get_user)):
    require_business(user, code)
    if start > end:
        raise HTTPException(400, "start must not be after end")
    with engine.connect() as conn:
        rows = conn.execute(text(DAILY_SQL[code]), {"s": start, "e": end}).all()
    audit.write(user["id"], "view_data", f"{code} {start} to {end}")
    return {"business": code, "metric": METRIC[code],
            "data": [{"date": r[0].isoformat(), "value": r[1]} for r in rows]}


@app.get("/businesses/{code}/forecast")
def forecast(code: str, user=Depends(get_user)):
    require_business(user, code)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT f.target_date, f.predicted_value::float, f.model_name "
                 "FROM forecasts f JOIN businesses b ON b.id = f.business_id "
                 "WHERE b.code = :c ORDER BY f.target_date"), {"c": code}).all()
    audit.write(user["id"], "view_forecast", code)
    return {"business": code, "metric": METRIC[code],
            "data": [{"date": r[0].isoformat(), "predicted": r[1],
                      "model": r[2]} for r in rows]}


@app.post("/ask")
def ask_question(body: Question, user=Depends(get_user)):
    result = assistant.ask(body.question, user["businesses"])
    if result["status"] == "forbidden":
        audit.write(user["id"], "access_denied", f"ask business={result['business']}")
        raise HTTPException(403, "You do not have access to this business")
    audit.write(user["id"], "question", f"{result['status']}: {body.question[:300]}")
    return result


@app.get("/audit-log")
def audit_log(limit: int = 100, user=Depends(get_user)):
    if user["role"] != "admin":
        audit.write(user["id"], "access_denied", "audit-log")
        raise HTTPException(403, "Admins only")
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT a.id, u.username, a.action, a.detail, a.created_at "
                 "FROM audit_log a LEFT JOIN users u ON u.id = a.user_id "
                 "ORDER BY a.id DESC LIMIT :n"), {"n": min(limit, 500)}).all()
    return [{"id": r[0], "user": r[1], "action": r[2], "detail": r[3],
             "at": r[4].isoformat()} for r in rows]