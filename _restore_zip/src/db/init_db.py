from __future__ import annotations

import sqlite3
from pathlib import Path

from src.core.config import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS measurements (
    id INTEGER PRIMARY KEY,
    ts_utc TEXT NOT NULL,
    -- Channel A1 (3-phase + meter 1)
    a1_production_kwh REAL DEFAULT 0,
    a1_consumption_kwh REAL DEFAULT 0,
    -- Channel B1 (3-phase + meter 1)
    b1_production_kwh REAL DEFAULT 0,
    b1_consumption_kwh REAL DEFAULT 0,
    -- Channel C1 (3-phase + meter 1)
    c1_production_kwh REAL DEFAULT 0,
    c1_consumption_kwh REAL DEFAULT 0,
    -- Channel A2 (3-phase + meter 2)
    a2_production_kwh REAL DEFAULT 0,
    a2_consumption_kwh REAL DEFAULT 0,
    -- Channel B2 (3-phase + meter 2)
    b2_production_kwh REAL DEFAULT 0,
    b2_consumption_kwh REAL DEFAULT 0,
    -- Channel C2 (3-phase + meter 2)
    c2_production_kwh REAL DEFAULT 0,
    c2_consumption_kwh REAL DEFAULT 0,
    -- Aggregated totals
    total_production_kwh REAL DEFAULT 0,
    total_consumption_kwh REAL DEFAULT 0,
    -- Global properties
    voltage_v REAL,
    frequency_hz REAL,
    power_factor REAL,
    quality_flag INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS system_events (
    id INTEGER PRIMARY KEY,
    ts_utc TEXT NOT NULL,
    level TEXT NOT NULL,
    source TEXT NOT NULL,
    message TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'admin'
);
"""


def init_database() -> Path:
    db_path = settings.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
    return db_path


if __name__ == "__main__":
    created = init_database()
    print(f"Database ready: {created}")
