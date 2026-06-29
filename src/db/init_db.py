from __future__ import annotations

import sqlite3
from pathlib import Path

from src.core.config import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS measurements (
	id INTEGER PRIMARY KEY,
	ts_utc TEXT NOT NULL,
	a1_production_kwh REAL DEFAULT 0,
	a1_consumption_kwh REAL DEFAULT 0,
	b1_production_kwh REAL DEFAULT 0,
	b1_consumption_kwh REAL DEFAULT 0,
	c1_production_kwh REAL DEFAULT 0,
	c1_consumption_kwh REAL DEFAULT 0,
	a2_production_kwh REAL DEFAULT 0,
	a2_consumption_kwh REAL DEFAULT 0,
	b2_production_kwh REAL DEFAULT 0,
	b2_consumption_kwh REAL DEFAULT 0,
	c2_production_kwh REAL DEFAULT 0,
	c2_consumption_kwh REAL DEFAULT 0,
	total_production_kwh REAL DEFAULT 0,
	total_consumption_kwh REAL DEFAULT 0,
	voltage_v REAL,
	frequency_hz REAL,
	power_factor REAL,
	quality_flag INTEGER DEFAULT 1,
	a1_power_w REAL,
	b1_power_w REAL,
	c1_power_w REAL,
	a2_power_w REAL,
	b2_power_w REAL,
	c2_power_w REAL
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

CREATE INDEX IF NOT EXISTS idx_measurements_ts_utc ON measurements(ts_utc);
CREATE INDEX IF NOT EXISTS idx_measurements_quality ON measurements(quality_flag);
CREATE INDEX IF NOT EXISTS idx_system_events_ts_utc ON system_events(ts_utc);

CREATE TABLE IF NOT EXISTS power_slots (
	slot_start_utc TEXT NOT NULL,
	slot_minutes INTEGER NOT NULL DEFAULT 15,
	slot_index INTEGER NOT NULL,
	c1_avg_w REAL,
	a2_avg_w REAL,
	b2_avg_w REAL,
	c2_avg_w REAL,
	c1_sample_count INTEGER NOT NULL DEFAULT 0,
	a2_sample_count INTEGER NOT NULL DEFAULT 0,
	b2_sample_count INTEGER NOT NULL DEFAULT 0,
	c2_sample_count INTEGER NOT NULL DEFAULT 0,
	quality_flag INTEGER NOT NULL DEFAULT 1,
	PRIMARY KEY (slot_start_utc, slot_minutes)
);

CREATE INDEX IF NOT EXISTS idx_power_slots_slot_index ON power_slots(slot_index);
"""


_POWER_W_COLUMNS = ("a1_power_w", "b1_power_w", "c1_power_w", "a2_power_w", "b2_power_w", "c2_power_w")


def _migrate_measurements_columns(conn: sqlite3.Connection) -> None:
	existing = {row[1] for row in conn.execute("PRAGMA table_info(measurements)")}
	for column in _POWER_W_COLUMNS:
		if column not in existing:
			conn.execute(f"ALTER TABLE measurements ADD COLUMN {column} REAL")


def init_database(db_path: Path | None = None) -> Path:
	target = db_path or settings.db_path
	target.parent.mkdir(parents=True, exist_ok=True)
	with sqlite3.connect(target) as conn:
		conn.execute("PRAGMA journal_mode=WAL")
		conn.executescript(SCHEMA)
		_migrate_measurements_columns(conn)
		conn.commit()
	return target


if __name__ == "__main__":
	created = init_database()
	print(f"Database ready: {created}")
