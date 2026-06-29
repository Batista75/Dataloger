#!/usr/bin/env python3
"""Invert C1 power polarity for today and replay C1 kWh indexes."""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")


def create_backup(db_path: Path) -> Path:
	stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
	backup_path = db_path.with_suffix(db_path.suffix + f".bak_c1_invert_{stamp}")
	with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as backup:
		source.backup(backup)
	return backup_path


def paris_day_start_utc(day: datetime | None = None) -> datetime:
	now = day or datetime.now(PARIS)
	start = now.replace(hour=0, minute=0, second=0, microsecond=0)
	return start.astimezone(timezone.utc)


def parse_ts(value: str) -> datetime:
	return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def invert_c1_power_w_only(db_path: Path, day_start: datetime) -> int:
	day_start_iso = day_start.isoformat()
	with sqlite3.connect(db_path) as conn:
		cur = conn.execute(
			"""
			UPDATE measurements
			SET c1_power_w = -c1_power_w
			WHERE ts_utc >= ? AND c1_power_w IS NOT NULL
			""",
			(day_start_iso,),
		)
		conn.commit()
		return int(cur.rowcount or 0)


def replay_c1_indices(db_path: Path, day_start: datetime) -> tuple[int, int]:
	day_start_iso = day_start.isoformat()
	with sqlite3.connect(db_path) as conn:
		conn.row_factory = sqlite3.Row
		baseline = conn.execute(
			"""
			SELECT c1_consumption_kwh, c1_production_kwh
			FROM measurements
			WHERE ts_utc < ?
			ORDER BY ts_utc DESC
			LIMIT 1
			""",
			(day_start_iso,),
		).fetchone()
		c1_cons = float(baseline["c1_consumption_kwh"] or 0.0) if baseline else 0.0
		c1_prod = float(baseline["c1_production_kwh"] or 0.0) if baseline else 0.0

		rows = conn.execute(
			"""
			SELECT id, ts_utc, c1_power_w, c1_consumption_kwh, c1_production_kwh,
				total_consumption_kwh, total_production_kwh
			FROM measurements
			WHERE ts_utc >= ?
			ORDER BY ts_utc ASC
			""",
			(day_start_iso,),
		).fetchall()

		if not rows:
			return 0, 0

		prev_row = conn.execute(
			"SELECT ts_utc FROM measurements WHERE ts_utc < ? ORDER BY ts_utc DESC LIMIT 1",
			(day_start_iso,),
		).fetchone()
		prev_ts = parse_ts(str(prev_row["ts_utc"])) if prev_row else day_start

		power_inverted = 0
		index_updated = 0

		for row in rows:
			row_id = int(row["id"])
			cur_ts = parse_ts(str(row["ts_utc"]))
			power_w = row["c1_power_w"]
			if power_w is not None:
				power_w = -float(power_w)
				power_inverted += 1
				conn.execute(
					"UPDATE measurements SET c1_power_w = ? WHERE id = ?",
					(round(power_w, 3), row_id),
				)

			delta_s = (cur_ts - prev_ts).total_seconds()
			if power_w is not None and 0 < delta_s <= 900:
				energy_delta = abs(float(power_w)) * delta_s / 3_600_000.0
				if float(power_w) >= 0:
					c1_cons += energy_delta
				else:
					c1_prod += energy_delta

			old_cons = float(row["c1_consumption_kwh"] or 0.0)
			old_prod = float(row["c1_production_kwh"] or 0.0)
			total_cons = float(row["total_consumption_kwh"] or 0.0) - old_cons + c1_cons
			total_prod = float(row["total_production_kwh"] or 0.0) - old_prod + c1_prod

			conn.execute(
				"""
				UPDATE measurements
				SET c1_consumption_kwh = ?, c1_production_kwh = ?,
					total_consumption_kwh = ?, total_production_kwh = ?
				WHERE id = ?
				""",
				(round(c1_cons, 6), round(c1_prod, 6), round(total_cons, 6), round(total_prod, 6), row_id),
			)
			index_updated += 1
			prev_ts = cur_ts

		conn.commit()
		return power_inverted, index_updated


def main() -> int:
	parser = argparse.ArgumentParser(description="Invert C1 polarity for today's measurements.")
	parser.add_argument("--db", default="data/measurements.db")
	parser.add_argument("--dry-run", action="store_true")
	parser.add_argument(
		"--power-w-only",
		action="store_true",
		help="Invert c1_power_w only (do not replay C1 kWh indexes).",
	)
	args = parser.parse_args()

	db_path = Path(args.db)
	if not db_path.exists():
		raise FileNotFoundError(db_path)

	day_start = paris_day_start_utc()
	print(f"Jour local (Paris) depuis UTC: {day_start.isoformat()}")

	if args.dry_run:
		with sqlite3.connect(db_path) as conn:
			count = conn.execute(
				"SELECT COUNT(*) FROM measurements WHERE ts_utc >= ?",
				(day_start.isoformat(),),
			).fetchone()[0]
		print(f"dry-run: {count} lignes a traiter")
		return 0

	backup = create_backup(db_path)
	print(f"Sauvegarde: {backup}")
	if args.power_w_only:
		inverted = invert_c1_power_w_only(db_path, day_start)
		print(f"c1_power_w inverses: {inverted}")
		return 0
	inverted, updated = replay_c1_indices(db_path, day_start)
	print(f"c1_power_w inverses: {inverted}")
	print(f"lignes indexes C1 recalculees: {updated}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
