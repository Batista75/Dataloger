#!/usr/bin/env python3
"""Fix C1 measurements collected before the Refoss probe polarity correction."""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
CHANNELS = ("a1", "b1", "c1", "a2", "b2", "c2")


def create_backup(db_path: Path) -> Path:
	stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
	backup_path = db_path.with_suffix(db_path.suffix + f".bak_c1_prefix_{stamp}")
	with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as backup:
		source.backup(backup)
	return backup_path


def parse_ts(value: str) -> datetime:
	return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def signed_w_from_indices(
	prev_cons: float,
	prev_prod: float,
	cur_cons: float,
	cur_prod: float,
	delta_seconds: float,
) -> float | None:
	if delta_seconds <= 0 or delta_seconds > 900:
		return None
	d_cons = cur_cons - prev_cons
	d_prod = cur_prod - prev_prod
	if d_cons < -1e-9 or d_prod < -1e-9:
		return None
	if d_cons > 0 and d_prod > 0:
		delta_kwh = d_cons - d_prod
	elif d_cons > 0:
		delta_kwh = d_cons
	elif d_prod > 0:
		delta_kwh = -d_prod
	else:
		delta_kwh = 0.0
	return (delta_kwh * 3_600_000.0) / delta_seconds


def corrected_c1_power_w(raw_w: float, ts: datetime, invert_until: datetime) -> float:
	if ts < invert_until:
		return -float(raw_w)
	return float(raw_w)


def apply_power_corrections(
	db_path: Path,
	backup_path: Path,
	day_start: datetime,
	probe_fix_ts: datetime,
	invert_until: datetime,
) -> tuple[int, int]:
	updated_from_backup = 0
	backfilled = 0
	with sqlite3.connect(db_path) as live, sqlite3.connect(backup_path) as bak:
		live.row_factory = sqlite3.Row
		bak.row_factory = sqlite3.Row
		rows = live.execute(
			"""
			SELECT id, ts_utc, c1_power_w, c1_consumption_kwh, c1_production_kwh
			FROM measurements
			WHERE ts_utc >= ? AND ts_utc < ?
			ORDER BY ts_utc ASC
			""",
			(day_start.isoformat(), probe_fix_ts.isoformat()),
		).fetchall()

		prev_bak: sqlite3.Row | None = None
		for row in rows:
			row_id = int(row["id"])
			ts = parse_ts(str(row["ts_utc"]))
			bak_row = bak.execute(
				"""
				SELECT ts_utc, c1_power_w, c1_consumption_kwh, c1_production_kwh
				FROM measurements WHERE ts_utc = ?
				""",
				(row["ts_utc"],),
			).fetchone()
			if bak_row is None:
				prev_bak = None
				continue

			corrected: float | None = None
			raw_w = bak_row["c1_power_w"]
			if raw_w is not None:
				corrected = corrected_c1_power_w(float(raw_w), ts, invert_until)
			elif prev_bak is not None:
				prev_ts = parse_ts(str(prev_bak["ts_utc"]))
				delta_s = (ts - prev_ts).total_seconds()
				derived = signed_w_from_indices(
					float(prev_bak["c1_consumption_kwh"] or 0.0),
					float(prev_bak["c1_production_kwh"] or 0.0),
					float(bak_row["c1_consumption_kwh"] or 0.0),
					float(bak_row["c1_production_kwh"] or 0.0),
					delta_s,
				)
				if derived is not None:
					corrected = corrected_c1_power_w(derived, ts, invert_until)
					backfilled += 1

			if corrected is not None:
				live.execute(
					"UPDATE measurements SET c1_power_w = ? WHERE id = ?",
					(round(corrected, 3), row_id),
				)
				updated_from_backup += 1
			prev_bak = bak_row

		live.commit()
	return updated_from_backup, backfilled


def replay_c1_indices_from_day(db_path: Path, day_start: datetime) -> int:
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
			return 0

		prev_row = conn.execute(
			"SELECT ts_utc FROM measurements WHERE ts_utc < ? ORDER BY ts_utc DESC LIMIT 1",
			(day_start_iso,),
		).fetchone()
		prev_ts = parse_ts(str(prev_row["ts_utc"])) if prev_row else day_start

		updated = 0
		for row in rows:
			row_id = int(row["id"])
			cur_ts = parse_ts(str(row["ts_utc"]))
			power_w = row["c1_power_w"]

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
			updated += 1
			prev_ts = cur_ts

		conn.commit()
		return updated


def summarize_range(db_path: Path, from_ts: datetime, until_ts: datetime, label: str) -> None:
	with sqlite3.connect(db_path) as conn:
		row = conn.execute(
			"""
			SELECT COUNT(*) AS n,
				AVG(c1_power_w) AS avg_w,
				MIN(c1_power_w) AS min_w,
				MAX(c1_power_w) AS max_w,
				SUM(CASE WHEN c1_power_w > 50 THEN 1 ELSE 0 END) AS pos,
				SUM(CASE WHEN c1_power_w < -50 THEN 1 ELSE 0 END) AS neg,
				SUM(CASE WHEN c1_power_w IS NULL THEN 1 ELSE 0 END) AS nulls
			FROM measurements
			WHERE ts_utc >= ? AND ts_utc < ?
			""",
			(from_ts.isoformat(), until_ts.isoformat()),
		).fetchone()
	print(
		f"{label}: lignes={row[0]} nulls={row[6]} avg={row[1]:.1f}W "
		f"min={row[2]:.1f} max={row[3]:.1f} pos={row[4]} neg={row[5]}"
	)


def main() -> int:
	parser = argparse.ArgumentParser(description="Fix C1 before Refoss probe polarity correction.")
	parser.add_argument("--db", default="data/measurements.db")
	parser.add_argument("--backup", default="data/measurements.db.bak_c1_invert_20260629_113404")
	parser.add_argument(
		"--probe-fix-ts",
		default="2026-06-29T11:10:52+00:00",
		help="Instant where probe polarity was corrected in Refoss (UTC ISO).",
	)
	parser.add_argument(
		"--invert-until",
		default="2026-06-29T11:01:28+00:00",
		help="Last instant still on inverted probe (UTC ISO). Before this: multiply by -1.",
	)
	parser.add_argument("--dry-run", action="store_true")
	args = parser.parse_args()

	db_path = Path(args.db)
	backup_path = Path(args.backup)
	if not db_path.exists():
		raise FileNotFoundError(db_path)
	if not backup_path.exists():
		raise FileNotFoundError(backup_path)

	probe_fix_ts = parse_ts(args.probe_fix_ts)
	invert_until = parse_ts(args.invert_until)
	day_start = probe_fix_ts.astimezone(PARIS).replace(
		hour=0, minute=0, second=0, microsecond=0
	).astimezone(timezone.utc)

	print(f"Jour Paris depuis {day_start.isoformat()}")
	print(f"Sonde inversee jusqu'a {invert_until.isoformat()}")
	print(f"Correction sonde Refoss a {probe_fix_ts.isoformat()}")
	print("Avant correction:")
	summarize_range(db_path, day_start, probe_fix_ts, "pre-fix")

	if args.dry_run:
		with sqlite3.connect(db_path) as conn:
			count = conn.execute(
				"SELECT COUNT(*) FROM measurements WHERE ts_utc >= ? AND ts_utc < ?",
				(day_start.isoformat(), probe_fix_ts.isoformat()),
			).fetchone()[0]
		print(f"dry-run: {count} lignes dans la plage pre-fix")
		return 0

	backup = create_backup(db_path)
	print(f"Sauvegarde: {backup}")

	updated, backfilled = apply_power_corrections(
		db_path, backup_path, day_start, probe_fix_ts, invert_until
	)
	print(f"c1_power_w corriges: {updated} (dont backfill index: {backfilled})")

	replayed = replay_c1_indices_from_day(db_path, day_start)
	print(f"indexes C1 rejoues sur la journee: {replayed}")

	print("Apres correction:")
	summarize_range(db_path, day_start, probe_fix_ts, "pre-fix")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
