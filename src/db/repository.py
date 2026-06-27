from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class Measurement:
	ts_utc: str
	a1_production_kwh: float | None = None
	a1_consumption_kwh: float | None = None
	b1_production_kwh: float | None = None
	b1_consumption_kwh: float | None = None
	c1_production_kwh: float | None = None
	c1_consumption_kwh: float | None = None
	a2_production_kwh: float | None = None
	a2_consumption_kwh: float | None = None
	b2_production_kwh: float | None = None
	b2_consumption_kwh: float | None = None
	c2_production_kwh: float | None = None
	c2_consumption_kwh: float | None = None
	total_production_kwh: float | None = None
	total_consumption_kwh: float | None = None
	voltage_v: float | None = None
	frequency_hz: float | None = None
	power_factor: float | None = None
	quality_flag: int = 1


class MeasurementRepository:
	def __init__(self, db_path: Path) -> None:
		self.db_path = db_path

	def _connect(self) -> sqlite3.Connection:
		conn = sqlite3.connect(self.db_path)
		conn.row_factory = sqlite3.Row
		return conn

	def insert_measurement(self, measurement: Measurement) -> None:
		query = """
		INSERT INTO measurements (
			ts_utc,
			a1_production_kwh, a1_consumption_kwh,
			b1_production_kwh, b1_consumption_kwh,
			c1_production_kwh, c1_consumption_kwh,
			a2_production_kwh, a2_consumption_kwh,
			b2_production_kwh, b2_consumption_kwh,
			c2_production_kwh, c2_consumption_kwh,
			total_production_kwh, total_consumption_kwh,
			voltage_v, frequency_hz, power_factor, quality_flag
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		"""
		values = (
			measurement.ts_utc,
			measurement.a1_production_kwh,
			measurement.a1_consumption_kwh,
			measurement.b1_production_kwh,
			measurement.b1_consumption_kwh,
			measurement.c1_production_kwh,
			measurement.c1_consumption_kwh,
			measurement.a2_production_kwh,
			measurement.a2_consumption_kwh,
			measurement.b2_production_kwh,
			measurement.b2_consumption_kwh,
			measurement.c2_production_kwh,
			measurement.c2_consumption_kwh,
			measurement.total_production_kwh,
			measurement.total_consumption_kwh,
			measurement.voltage_v,
			measurement.frequency_hz,
			measurement.power_factor,
			measurement.quality_flag,
		)
		with self._connect() as conn:
			conn.execute(query, values)
			conn.commit()

	def get_latest(self) -> dict[str, Any] | None:
		query = """
		SELECT ts_utc,
			a1_production_kwh, a1_consumption_kwh,
			b1_production_kwh, b1_consumption_kwh,
			c1_production_kwh, c1_consumption_kwh,
			a2_production_kwh, a2_consumption_kwh,
			b2_production_kwh, b2_consumption_kwh,
			c2_production_kwh, c2_consumption_kwh,
			total_production_kwh, total_consumption_kwh,
			voltage_v, frequency_hz, power_factor, quality_flag
		FROM measurements
		ORDER BY id DESC
		LIMIT 1
		"""
		with self._connect() as conn:
			row = conn.execute(query).fetchone()
		if row is None:
			return None
		return dict(row)

	def get_range(self, from_ts_utc: str, to_ts_utc: str, limit: int = 2000) -> list[dict[str, Any]]:
		query = """
		SELECT ts_utc,
			a1_production_kwh, a1_consumption_kwh,
			b1_production_kwh, b1_consumption_kwh,
			c1_production_kwh, c1_consumption_kwh,
			a2_production_kwh, a2_consumption_kwh,
			b2_production_kwh, b2_consumption_kwh,
			c2_production_kwh, c2_consumption_kwh,
			total_production_kwh, total_consumption_kwh,
			voltage_v, frequency_hz, power_factor, quality_flag
		FROM measurements
		WHERE ts_utc >= ? AND ts_utc <= ?
		ORDER BY ts_utc ASC
		LIMIT ?
		"""
		with self._connect() as conn:
			rows = conn.execute(query, (from_ts_utc, to_ts_utc, limit)).fetchall()
		return [dict(row) for row in rows]

	def log_event(self, level: str, source: str, message: str, ts_utc: str) -> None:
		with self._connect() as conn:
			conn.execute(
				"INSERT INTO system_events (ts_utc, level, source, message) VALUES (?, ?, ?, ?)",
				(ts_utc, level, source, message),
			)
			conn.commit()

	def as_dict(self, measurement: Measurement) -> dict[str, Any]:
		return asdict(measurement)
