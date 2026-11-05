CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    full_name VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('manager', 'planner', 'admin')),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS businesses (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS user_businesses (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, business_id)
);

CREATE TABLE IF NOT EXISTS locations (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id),
    name VARCHAR(100) NOT NULL,
    UNIQUE (business_id, name)
);

CREATE TABLE IF NOT EXISTS ridership_daily (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    location_id INTEGER NOT NULL REFERENCES locations(id),
    ticket_type VARCHAR(30) NOT NULL,
    passengers INTEGER NOT NULL CHECK (passengers >= 0),
    UNIQUE (date, location_id, ticket_type)
);

CREATE TABLE IF NOT EXISTS hotel_daily (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    location_id INTEGER NOT NULL REFERENCES locations(id),
    rooms_available INTEGER NOT NULL CHECK (rooms_available >= 0),
    rooms_booked INTEGER NOT NULL CHECK (rooms_booked >= 0),
    avg_room_rate_jpy INTEGER NOT NULL CHECK (avg_room_rate_jpy >= 0),
    UNIQUE (date, location_id),
    CHECK (rooms_booked <= rooms_available)
);

CREATE TABLE IF NOT EXISTS weather_daily (
    date DATE PRIMARY KEY,
    temperature_c NUMERIC(4,1) NOT NULL,
    rainfall_mm NUMERIC(5,1) NOT NULL CHECK (rainfall_mm >= 0),
    sunshine_hours NUMERIC(3,1) NOT NULL CHECK (sunshine_hours >= 0)
);

CREATE TABLE IF NOT EXISTS holidays (
    date DATE PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    CHECK (end_date >= start_date)
);

CREATE TABLE IF NOT EXISTS forecasts (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id),
    target_date DATE NOT NULL,
    metric VARCHAR(30) NOT NULL,
    predicted_value NUMERIC(12,2) NOT NULL,
    model_name VARCHAR(50) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reports (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id),
    week_start DATE NOT NULL,
    file_path VARCHAR(255) NOT NULL,
    generated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    generated_by INTEGER REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    action VARCHAR(50) NOT NULL,
    detail TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ridership_date ON ridership_daily(date);
CREATE INDEX IF NOT EXISTS idx_hotel_date ON hotel_daily(date);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);

CREATE TABLE IF NOT EXISTS park_daily (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    location_id INTEGER NOT NULL REFERENCES locations(id),
    visitors INTEGER NOT NULL CHECK (visitors >= 0),
    avg_wait_minutes INTEGER NOT NULL CHECK (avg_wait_minutes >= 0),
    revenue_jpy BIGINT NOT NULL CHECK (revenue_jpy >= 0),
    UNIQUE (date, location_id)
);

CREATE TABLE IF NOT EXISTS anomalies (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id),
    date DATE NOT NULL,
    metric VARCHAR(30) NOT NULL,
    observed NUMERIC(12,2) NOT NULL,
    expected NUMERIC(12,2) NOT NULL,
    score NUMERIC(6,2) NOT NULL,
    detected_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (business_id, date, metric)
);

CREATE TABLE IF NOT EXISTS data_quality_log (
    id SERIAL PRIMARY KEY,
    source_file VARCHAR(100) NOT NULL,
    issue_type VARCHAR(50) NOT NULL,
    detail TEXT,
    action_taken VARCHAR(100) NOT NULL,
    logged_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_park_date ON park_daily(date);