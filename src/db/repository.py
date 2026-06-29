from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from src.core.quality_flags import QUALITY_IMPORTED_DAILY, QUALITY_LIVE, QUALITY_SUSPECT


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
	a1_power_w: float | None = None
	b1_power_w: float | None = None
	c1_power_w: float | None = None
	a2_power_w: float | None = None
	b2_power_w: float | None = None
	c2_power_w: float | None = None


_MEASUREMENT_SELECT = """
	ts_utc,
	a1_production_kwh, a1_consumption_kwh,
	b1_production_kwh, b1_consumption_kwh,
	c1_production_kwh, c1_consumption_kwh,
	a2_production_kwh, a2_consumption_kwh,
	b2_production_kwh, b2_consumption_kwh,
	c2_production_kwh, c2_consumption_kwh,
	total_production_kwh, total_consumption_kwh,
	voltage_v, frequency_hz, power_factor, quality_flag,
	a1_power_w, b1_power_w, c1_power_w, a2_power_w, b2_power_w, c2_power_w
"""


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
			voltage_v, frequency_hz, power_factor, quality_flag,
			a1_power_w, b1_power_w, c1_power_w, a2_power_w, b2_power_w, c2_power_w
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
			measurement.a1_power_w,
			measurement.b1_power_w,
			measurement.c1_power_w,
			measurement.a2_power_w,
			measurement.b2_power_w,
			measurement.c2_power_w,
		)
		with self._connect() as conn:
			conn.execute(query, values)
			conn.commit()

	def get_latest(self) -> dict[str, Any] | None:
		query = f"""
		SELECT {_MEASUREMENT_SELECT}
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
		query = f"""
		SELECT {_MEASUREMENT_SELECT}
		FROM measurements
		WHERE ts_utc >= ? AND ts_utc <= ?
		ORDER BY ts_utc ASC
		LIMIT ?
		"""
		with self._connect() as conn:
			rows = conn.execute(query, (from_ts_utc, to_ts_utc, limit)).fetchall()
		return [dict(row) for row in rows]

	def get_range_all(self, from_ts_utc: str, to_ts_utc: str) -> list[dict[str, Any]]:
		query = f"""
		SELECT {_MEASUREMENT_SELECT}
		FROM measurements
		WHERE ts_utc >= ? AND ts_utc <= ?
		ORDER BY ts_utc ASC
		"""
		with self._connect() as conn:
			rows = conn.execute(query, (from_ts_utc, to_ts_utc)).fetchall()
		return [dict(row) for row in rows]

	def get_recent(self, limit: int = 3000) -> list[dict[str, Any]]:
		query = f"""
		SELECT {_MEASUREMENT_SELECT}
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
				SUM(CASE WHEN quality_flag = 1 THEN 1 ELSE 0 END) AS live_rows,
				MAX(CASE WHEN quality_flag = 2 THEN c1_consumption_kwh END) AS imp_c1_cons,
				MIN(CASE WHEN quality_flag = 1 THEN c1_consumption_kwh END) AS live_c1_cons_min,
				MAX(CASE WHEN quality_flag = 1 THEN c1_consumption_kwh END) AS live_c1_cons_max,
				MAX(CASE WHEN quality_flag = 2 THEN c1_production_kwh END) AS imp_c1_prod,
				MIN(CASE WHEN quality_flag = 1 THEN c1_production_kwh END) AS live_c1_prod_min,
				MAX(CASE WHEN quality_flag = 1 THEN c1_production_kwh END) AS live_c1_prod_max,
				MAX(CASE WHEN quality_flag = 2 THEN a2_production_kwh END) AS imp_a2_prod,
				MIN(CASE WHEN quality_flag = 1 THEN a2_production_kwh END) AS live_a2_prod_min,
				MAX(CASE WHEN quality_flag = 1 THEN a2_production_kwh END) AS live_a2_prod_max
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

	def get_energy_deltas_since(self, from_ts_utc: str) -> dict[str, Any]:
		"""Aggregate C1/A2 index deltas since from_ts_utc (live rows only, single SQL pass)."""
		query = """
		SELECT
			COUNT(*) AS sample_count,
			MIN(c1_consumption_kwh) AS c1_cons_min,
			MAX(c1_consumption_kwh) AS c1_cons_max,
			MIN(c1_production_kwh) AS c1_prod_min,
			MAX(c1_production_kwh) AS c1_prod_max,
			MIN(a2_production_kwh) AS a2_prod_min,
			MAX(a2_production_kwh) AS a2_prod_max,
			MIN(ts_utc) AS first_ts_utc,
			MAX(ts_utc) AS last_ts_utc
		FROM measurements
		WHERE ts_utc >= ? AND quality_flag NOT IN (?, ?)
		"""
		with self._connect() as conn:
			row = conn.execute(query, (from_ts_utc, QUALITY_IMPORTED_DAILY, QUALITY_SUSPECT)).fetchone()
		if row is None:
			return {
				"sample_count": 0,
				"c1_cons_min": None,
				"c1_cons_max": None,
				"c1_prod_min": None,
				"c1_prod_max": None,
				"a2_prod_min": None,
				"a2_prod_max": None,
				"first_ts_utc": None,
				"last_ts_utc": None,
			}
		return dict(row)

	def log_event(self, level: str, source: str, message: str, ts_utc: str) -> None:
		with self._connect() as conn:
			conn.execute(
				"INSERT INTO system_events (ts_utc, level, source, message) VALUES (?, ?, ?, ?)",
				(ts_utc, level, source, message),
			)
			conn.commit()

	def as_dict(self, measurement: Measurement) -> dict[str, Any]:
		return asdict(measurement)

	def upsert_power_slot(self, slot: dict[str, Any]) -> None:
		query = """
		INSERT INTO power_slots (
			slot_start_utc, slot_minutes, slot_index,
			c1_avg_w, a2_avg_w, b2_avg_w, c2_avg_w,
			c1_sample_count, a2_sample_count, b2_sample_count, c2_sample_count,
			quality_flag
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(slot_start_utc, slot_minutes) DO UPDATE SET
			slot_index = excluded.slot_index,
			c1_avg_w = excluded.c1_avg_w,
			a2_avg_w = excluded.a2_avg_w,
			b2_avg_w = excluded.b2_avg_w,
			c2_avg_w = excluded.c2_avg_w,
			c1_sample_count = excluded.c1_sample_count,
			a2_sample_count = excluded.a2_sample_count,
			b2_sample_count = excluded.b2_sample_count,
			c2_sample_count = excluded.c2_sample_count,
			quality_flag = excluded.quality_flag
		"""
		values = (
			slot["slot_start_utc"],
			int(slot["slot_minutes"]),
			int(slot["slot_index"]),
			slot.get("c1_avg_w"),
			slot.get("a2_avg_w"),
			slot.get("b2_avg_w"),
			slot.get("c2_avg_w"),
			int(slot.get("c1_sample_count") or 0),
			int(slot.get("a2_sample_count") or 0),
			int(slot.get("b2_sample_count") or 0),
			int(slot.get("c2_sample_count") or 0),
			int(slot.get("quality_flag") or QUALITY_LIVE),
		)
		with self._connect() as conn:
			conn.execute(query, values)
			conn.commit()

	def get_latest_power_slot_start(self, slot_minutes: int) -> str | None:
		query = """
		SELECT slot_start_utc FROM power_slots
		WHERE slot_minutes = ?
		ORDER BY slot_start_utc DESC
		LIMIT 1
		"""
		with self._connect() as conn:
			row = conn.execute(query, (slot_minutes,)).fetchone()
		if row is None:
			return None
		return str(row[0])

	def count_measurements_before(
		self,
		before_ts_utc: str,
		quality_flags: tuple[int, ...] | None = None,
	) -> int:
		if quality_flags:
			placeholders = ",".join("?" for _ in quality_flags)
			query = f"SELECT COUNT(*) FROM measurements WHERE ts_utc < ? AND quality_flag IN ({placeholders})"
			params: tuple[Any, ...] = (before_ts_utc, *quality_flags)
		else:
			query = "SELECT COUNT(*) FROM measurements WHERE ts_utc < ?"
			params = (before_ts_utc,)
		with self._connect() as conn:
			row = conn.execute(query, params).fetchone()
		return int(row[0]) if row else 0

	def purge_measurements_before(
		self,
		before_ts_utc: str,
		quality_flags: tuple[int, ...] | None = None,
	) -> int:
		if quality_flags:
			placeholders = ",".join("?" for _ in quality_flags)
			query = f"DELETE FROM measurements WHERE ts_utc < ? AND quality_flag IN ({placeholders})"
			params: tuple[Any, ...] = (before_ts_utc, *quality_flags)
		else:
			query = "DELETE FROM measurements WHERE ts_utc < ?"
			params = (before_ts_utc,)
		with self._connect() as conn:
			cur = conn.execute(query, params)
			deleted = cur.rowcount
			conn.commit()
		return int(deleted) if deleted >= 0 else 0

	def get_power_slots_for_day(
		self,
		day_start_utc: str,
		day_end_utc: str,
		slot_minutes: int,
	) -> list[dict[str, Any]]:
		query = """
		SELECT slot_start_utc, slot_minutes, slot_index,
			c1_avg_w, a2_avg_w, b2_avg_w, c2_avg_w,
			c1_sample_count, a2_sample_count, b2_sample_count, c2_sample_count,
			quality_flag
		FROM power_slots
		WHERE slot_minutes = ? AND slot_start_utc >= ? AND slot_start_utc < ?
		ORDER BY slot_start_utc ASC
		"""
		with self._connect() as conn:
			rows = conn.execute(query, (slot_minutes, day_start_utc, day_end_utc)).fetchall()
		return [dict(row) for row in rows]

	def mark_suspect_measurements_before_trusted_cutoff(
		self,
		unreliable_from: str,
		unreliable_until: str,
		local_start_hhmm: str = "14:00",
	) -> int:
		"""Mark live rows before daily trusted cutoff as QUALITY_SUSPECT (step 1)."""
		from src.core.chart_power import PARIS, resolve_trusted_chart_from, _parse_iso_date

		start_date = _parse_iso_date(unreliable_from)
		end_date = _parse_iso_date(unreliable_until)
		if start_date is None or end_date is None:
			return 0

		total = 0
		day = start_date
		while day <= end_date:
			local_midnight = datetime(day.year, day.month, day.day, tzinfo=PARIS)
			day_start = local_midnight.astimezone(timezone.utc)
			trusted_from = resolve_trusted_chart_from(
				day_start,
				unreliable_from=start_date,
				unreliable_until=end_date,
				local_start_hhmm=local_start_hhmm,
			)
			next_day = day_start + timedelta(days=1)
			with self._connect() as conn:
				cur = conn.execute(
					"""
					UPDATE measurements
					SET quality_flag = ?
					WHERE quality_flag = ?
						AND ts_utc >= ? AND ts_utc < ?
						AND ts_utc < ?
					""",
					(QUALITY_SUSPECT, QUALITY_LIVE, day_start.isoformat(), next_day.isoformat(), trusted_from.isoformat()),
				)
				total += int(cur.rowcount or 0)
				conn.commit()
			day = day + timedelta(days=1)
		return total
