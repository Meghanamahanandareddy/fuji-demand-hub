# Mt. Fuji Tourism Demand Hub

A pilot analytics platform built for the Fuji Kyuko Group's DX work. It brings
railway, hotel, and amusement park data into one place, forecasts next week's
demand, flags unusual days automatically, and controls who can see what.

> **All data is synthetic.** 
## The problem

Railways, hotels, and the park all depend on the same visitors, but each tracks its
own data. Reports are built by hand, planning decisions use only part of the
picture, and simple questions need someone to pull data first.

## What it does

| Feature | Detail |
|---|---|
| **Data pipeline** | Cleans raw files (mixed date formats, blanks, duplicates, inconsistent names, impossible values) and loads them into PostgreSQL. Every fix is written to a data-quality log. Safe to rerun with no duplicates |
| **Dashboard** | Railway, hotels, amusement park, and a cross-business view showing how demand and weather move together |
| **Forecasting** | Four models compared on a held-out month (October 2026). Best calendar-based model: 6.7% error for railway, 7.6% for hotels, 12.6% for the park |
| **Anomaly detection** | Finds unusual days by comparing each day with what the calendar predicts. It found the planted typhoon (16 to 20 Sep 2025) in all three businesses without being told about it |
| **Secure API** | FastAPI with salted password hashing, signed login tokens, role-based access (manager, planner, admin), and an audit log |
| **Tests** | Automated tests, including: a hotel manager cannot view railway data |

## Screenshots

### Railway demand, with the typhoon dip in September 2025
![Railway](docs/images/railway.png)

### How the businesses move together, and what drives demand
Railway, hotel and park demand are strongly linked (0.91 to 0.96), and rainfall
pushes all three down.

![Cross-business](docs/images/cross-business.png)

### Forecasts and model comparison
![Forecast](docs/images/forecast.png)

### Unusual days found automatically
The five major days are the typhoon (rainfall 148 to 210 mm). The detector was
never told about the storm.

![Unusual days](docs/images/anomalies.png)

## Security

- Passwords are hashed (PBKDF2, 200,000 rounds) and never stored in plain text
- Login tokens are signed and expire after 8 hours
- Credentials and secrets are read from environment variables, not from code
- A user sees a business only if the database grants it; the default is deny
- Every login, data view, and refused request is written to an audit log that
  only admins can read
- Automated tests check these rules, for example that a hotel manager is refused
  railway data and that the refusal is audited

## Tech

Python 3.11, PostgreSQL 17, pandas, scikit-learn, statsmodels, FastAPI,
SQLAlchemy, Streamlit, Plotly, pytest.

## Run it locally

```
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a PostgreSQL database and a `.env` file:

```
DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@localhost:5432/fuji_demand
SECRET_KEY=a-long-random-string
```

Then run, in order:

```
python scripts/create_tables.py
python scripts/seed_reference.py
python scripts/generate_data.py
python scripts/etl.py
python scripts/forecast.py
python scripts/detect_anomalies.py
python scripts/create_users.py
streamlit run dashboard.py
uvicorn app.main:app --reload
pytest -v
```

## Limitations

- Synthetic data means the error figures are optimistic compared with real data
- One held-out month is limited evidence; more months should be tested
- Forecasts use calendar features only, because a weather forecast feed is not
  connected. Weather improves accuracy on the test month (park error drops from
  12.6% to 6.7%) and would be the first extension

## Roadmap (in progress)

- Natural-language question assistant with read-only SQL guardrails
- Automatic weekly PDF/Excel reports
- Login screen on the dashboard
- Deployment on AWS
- Automated tests on every commit

## Documents

- [Requirements](docs/01-requirements.md)