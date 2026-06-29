#!/usr/bin/env python3
"""Export chart-power slots (power_slots + live) for validation."""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
	sys.path.insert(0, str(ROOT))

from src.core.chart_power_query import fetch_chart_power_for_day  # noqa: E402
from src.core.config import settings
from src.db.repository import MeasurementRepository


def paris_day_start_utc(day: str) -> datetime:
	from datetime import timedelta

	try:
		from zoneinfo import ZoneInfo

		paris = ZoneInfo("Europe/Paris")
	except Exception:
		paris = timezone(timedelta(hours=2))
	dt = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=paris)
	start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
	return start.astimezone(timezone.utc)


def main() -> int:
	parser = argparse.ArgumentParser(description="Export chart power slots to CSV.")
	parser.add_argument("--db", default="data/measurements.db")
	parser.add_argument("--date", default=None, help="YYYY-MM-DD Paris (default: today)")
	parser.add_argument("--out", default=None)
	args = parser.parse_args()

	db_path = Path(args.db)
	if not db_path.exists():
		print(f"DB_NOT_FOUND={db_path}")
		return 1

	try:
		from zoneinfo import ZoneInfo

		paris = ZoneInfo("Europe/Paris")
	except Exception:
		from datetime import timedelta

		paris = timezone(timedelta(hours=2))

	day = args.date or datetime.now(paris).strftime("%Y-%m-%d")
	day_start = paris_day_start_utc(day)
	now = datetime.now(timezone.utc)

	repo = MeasurementRepository(db_path)
	result = fetch_chart_power_for_day(repo, settings, day_start, now=now)
	slots = result["data"]
	trusted_from = datetime.fromisoformat(result["trusted_from_utc"].replace("Z", "+00:00"))

	out = Path(args.out or f"exports/chart_power_{day.replace('-', '')}.csv")
	out.parent.mkdir(parents=True, exist_ok=True)

	fieldnames = [
		"slot_index",
		"ts_utc",
		"source",
		"c1_w",
		"a2_w",
		"b2_w",
		"c2_w",
		"autre_w",
		"c1_samples",
	]
	exported = 0
	with out.open("w", newline="", encoding="utf-8") as f:
		writer = csv.DictWriter(f, fieldnames=fieldnames)
		writer.writeheader()
		for point in slots:
			slot_ts = point.get("ts_utc")
			if slot_ts and datetime.fromisoformat(slot_ts.replace("Z", "+00:00")) < trusted_from:
				continue
			c1 = point.get("c1_signed_w")
			a2 = point.get("a2_signed_w")
			b2 = point.get("b2_signed_w")
			c2 = point.get("c2_signed_w")
			autre = None
			if all(v is not None for v in (c1, a2, b2, c2)):
				autre = float(c1) - (float(a2) + float(b2) + float(c2))
			if c1 is not None:
				exported += 1
			writer.writerow(
				{
					"slot_index": point.get("slot_index"),
					"ts_utc": slot_ts,
					"source": point.get("source", result.get("power_source")),
					"c1_w": c1,
					"a2_w": a2,
					"b2_w": b2,
					"c2_w": c2,
					"autre_w": round(autre, 1) if autre is not None else None,
					"c1_samples": point.get("c1_sample_count"),
				}
			)

	print(f"DATE={day}")
	print(f"POWER_SOURCE={result.get('power_source')}")
	print(f"PERSISTED_SLOTS={result.get('persisted_slot_count')}")
	print(f"RAW_SAMPLES={result.get('sample_count')}")
	print(f"TRUSTED_FROM={result['trusted_from_utc']}")
	print(f"SLOTS_EXPORTED={exported}")
	print(f"CSV={out.resolve()}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
