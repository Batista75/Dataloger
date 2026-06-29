#!/usr/bin/env python3
"""Export one local-day of measurements to CSV (Europe/Paris midnight bounds)."""
from __future__ import annotations

import argparse
import csv
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
	from zoneinfo import ZoneInfo

	PARIS = ZoneInfo("Europe/Paris")
except Exception:
	PARIS = timezone(timedelta(hours=2))


def paris_day_bounds(day: str) -> tuple[str, str]:
	dt = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=PARIS)
	start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
	end = start.replace(hour=23, minute=59, second=59, microsecond=999999)
	return start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()


def main() -> int:
	parser = argparse.ArgumentParser(description="Export measurements for one Paris local day.")
	parser.add_argument("--db", default="data/measurements.db")
	parser.add_argument("--date", default=None, help="YYYY-MM-DD (Paris). Default: today Paris.")
	parser.add_argument("--out", default=None, help="Output CSV path.")
	args = parser.parse_args()

	db_path = Path(args.db)
	if not db_path.exists():
		print(f"DB_NOT_FOUND={db_path}")
		return 1

	day = args.date or datetime.now(PARIS).strftime("%Y-%m-%d")
	from_ts, to_ts = paris_day_bounds(day)
	out = Path(args.out or f"exports/measurements_{day.replace('-', '')}.csv")

	with sqlite3.connect(db_path) as conn:
		conn.row_factory = sqlite3.Row
		columns = [r[1] for r in conn.execute("PRAGMA table_info(measurements)").fetchall()]
		rows = conn.execute(
			"""
			SELECT * FROM measurements
			WHERE ts_utc >= ? AND ts_utc <= ?
			ORDER BY ts_utc ASC, id ASC
			""",
			(from_ts, to_ts),
		).fetchall()

	out.parent.mkdir(parents=True, exist_ok=True)
	with out.open("w", newline="", encoding="utf-8") as f:
		writer = csv.writer(f)
		writer.writerow(columns)
		for row in rows:
			writer.writerow([row[c] for c in columns])

	print(f"DATE={day}")
	print(f"FROM={from_ts}")
	print(f"TO={to_ts}")
	print(f"ROWS={len(rows)}")
	print(f"CSV={out.resolve()}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
