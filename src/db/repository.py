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

	def get_recent(self, limit: int = 3000) -> list[dict[str, Any]]:
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
		LIMIT ?
		"""
		with self._connect() as conn:
			rows = conn.execute(query, (limit,)).fetchall()
		# Query returns newest first; reverse for chronological processing.
		return [dict(row) for row in reversed(rows)]

	def get_recent_quality(self, limit: int = 1200) -> list[dict[str, Any]]:
		query = """
		SELECT ts_utc,
			total_production_kwh,
			total_consumption_kwh,
			quality_flag
		FROM measurements
		ORDER BY id DESC
		LIMIT ?
		"""
		with self._connect() as conn:
			rows = conn.execute(query, (limit,)).fetchall()
		return [dict(row) for row in reversed(rows)]

	def get_daily_energy_summary(self, limit_days: int = 800) -> list[dict[str, Any]]:
		# C1 is the EDF grid reference (import - export, signed).
		# A2 is PV production. Live rows use cumulative indexes (daily = max-min);
		# imported history rows (quality_flag=2) store daily totals directly.
		query = """
		WITH daily AS (
			SELECT
				substr(ts_utc, 1, 10) AS day_utc,
				SUM(CASE WHEN quality_flag = 2 THEN 1 ELSE 0 END) AS imported_rows,
				SUM(CASE WHEN quality_flag != 2 THEN 1 ELSE 0 END) AS live_rows,
				MAX(CASE WHEN quality_flag = 2 THEN c1_consumption_kwh END) AS imp_c1_cons,
				MIN(CASE WHEN quality_flag != 2 THEN c1_consumption_kwh END) AS live_c1_cons_min,
				MAX(CASE WHEN quality_flag != 2 THEN c1_consumption_kwh END) AS live_c1_cons_max,
				MAX(CASE WHEN quality_flag = 2 THEN c1_production_kwh END) AS imp_c1_prod,
				MIN(CASE WHEN quality_flag != 2 THEN c1_production_kwh END) AS live_c1_prod_min,
				MAX(CASE WHEN quality_flag != 2 THEN c1_production_kwh END) AS live_c1_prod_max,
				MAX(CASE WHEN quality_flag = 2 THEN a2_production_kwh END) AS imp_a2_prod,
				MIN(CASE WHEN quality_flag != 2 THEN a2_production_kwh END) AS live_a2_prod_min,
				MAX(CASE WHEN quality_flag != 2 THEN a2_production_kwh END) AS live_a2_prod_max
			FROM measurements
			GROUP BY substr(ts_utc, 1, 10)
		),
		computed AS (
			SELECT
				day_utc,
				CASE
					WHEN live_rows >= 2
						AND live_c1_cons_max IS NOT NULL
						AND live_c1_cons_min IS NOT NULL
						AND live_c1_cons_max >= live_c1_cons_min
						THEN live_c1_cons_max - live_c1_cons_min
					WHEN imported_rows > 0 AND imp_c1_cons IS NOT NULL
						THEN imp_c1_cons
					WHEN live_rows > 0
						AND live_c1_cons_max IS NOT NULL
						AND live_c1_cons_min IS NOT NULL
						AND live_c1_cons_max >= live_c1_cons_min
						THEN live_c1_cons_max - live_c1_cons_min
					ELSE 0
				END AS grid_import_kwh,
				CASE
					WHEN live_rows >= 2
						AND live_c1_prod_max IS NOT NULL
						AND live_c1_prod_min IS NOT NULL
						AND live_c1_prod_max >= live_c1_prod_min
						THEN live_c1_prod_max - live_c1_prod_min
					WHEN imported_rows > 0 AND imp_c1_prod IS NOT NULL
						THEN imp_c1_prod
					WHEN live_rows > 0
						AND live_c1_prod_max IS NOT NULL
						AND live_c1_prod_min IS NOT NULL
						AND live_c1_prod_max >= live_c1_prod_min
						THEN live_c1_prod_max - live_c1_prod_min
					ELSE 0
				END AS grid_export_kwh,
				CASE
					WHEN live_rows >= 2
						AND live_a2_prod_max IS NOT NULL
						AND live_a2_prod_min IS NOT NULL
						AND live_a2_prod_max >= live_a2_prod_min
						THEN live_a2_prod_max - live_a2_prod_min
					WHEN imported_rows > 0 AND imp_a2_prod IS NOT NULL
						THEN imp_a2_prod
					WHEN live_rows > 0
						AND live_a2_prod_max IS NOT NULL
						AND live_a2_prod_min IS NOT NULL
						AND live_a2_prod_max >= live_a2_prod_min
						THEN live_a2_prod_max - live_a2_prod_min
					ELSE 0
				END AS pv_production_kwh
			FROM daily
		),
		enriched AS (
			SELECT
				day_utc,
				ROUND(grid_import_kwh, 6) AS grid_import_kwh,
				ROUND(grid_export_kwh, 6) AS grid_export_kwh,
				ROUND(pv_production_kwh, 6) AS pv_production_kwh,
				ROUND(grid_import_kwh - grid_export_kwh, 6) AS c1_net_kwh,
				ROUND(
					CASE
						WHEN pv_production_kwh - grid_export_kwh > 0
							THEN pv_production_kwh - grid_export_kwh
						ELSE 0
					END,
				6) AS autoconsumption_kwh,
				CASE
					WHEN pv_production_kwh > 0
						THEN ROUND(
							100.0 * CASE
								WHEN pv_production_kwh - grid_export_kwh > 0
									THEN pv_production_kwh - grid_export_kwh
								ELSE 0
							END / pv_production_kwh,
						3)
					ELSE NULL
				END AS autoconsumption_rate_pct
			FROM computed
		),
		windowed AS (
			SELECT *
			FROM enriched
			ORDER BY day_utc DESC
			LIMIT ?
		)
		SELECT
			day_utc AS date_utc,
			grid_import_kwh,
			grid_export_kwh,
			pv_production_kwh,
			c1_net_kwh,
			autoconsumption_kwh,
			autoconsumption_rate_pct
		FROM windowed
		ORDER BY date_utc ASC
		"""
		with self._connect() as conn:
			rows = conn.execute(query, (limit_days,)).fetchall()
		return [dict(row) for row in rows]

	def get_daily_consumption(self, limit_days: int = 800) -> list[dict[str, Any]]:
		return self.get_daily_energy_summary(limit_days=limit_days)

	def log_event(self, level: str, source: str, message: str, ts_utc: str) -> None:
		with self._connect() as conn:
			conn.execute(
				"INSERT INTO system_events (ts_utc, level, source, message) VALUES (?, ?, ?, ?)",
				(ts_utc, level, source, message),
			)
			conn.commit()

	def as_dict(self, measurement: Measurement) -> dict[str, Any]:
		return asdict(measurement)
