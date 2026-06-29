#!/usr/bin/env python3
"""Purge raw measurements older than RAW_RETENTION_DAYS (keeps imports + power_slots)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
	sys.path.insert(0, str(ROOT))

from src.core.config import settings  # noqa: E402
from src.core.maintenance import PURGE_QUALITY_FLAGS, purge_cutoff_utc, run_retention_purge  # noqa: E402
from src.db.repository import MeasurementRepository  # noqa: E402


def main() -> int:
	parser = argparse.ArgumentParser(description="Purge live/raw measurements older than retention.")
	parser.add_argument("--db", default=None, help="Override DB_PATH")
	parser.add_argument("--days", type=int, default=None, help="Override RAW_RETENTION_DAYS")
	parser.add_argument("--dry-run", action="store_true", help="Count only, no DELETE")
	args = parser.parse_args()

	db_path = Path(args.db or settings.db_path)
	if not db_path.exists():
		print(f"DB_NOT_FOUND={db_path}")
		return 1

	retention_days = args.days if args.days is not None else settings.raw_retention_days
	if args.days is not None:
		from dataclasses import replace

		settings_obj = replace(settings, raw_retention_days=retention_days)
	else:
		settings_obj = settings

	repo = MeasurementRepository(db_path)
	if args.dry_run:
		cutoff = purge_cutoff_utc(settings_obj)
		matched = repo.count_measurements_before(cutoff.isoformat(), quality_flags=PURGE_QUALITY_FLAGS)
		print(f"DRY_RUN=1")
		print(f"CUTOFF={cutoff.isoformat()}")
		print(f"RETENTION_DAYS={retention_days}")
		print(f"WOULD_DELETE={matched}")
		return 0

	stats = run_retention_purge(repo, settings_obj)
	print(f"CUTOFF={stats['cutoff_ts_utc']}")
	print(f"RETENTION_DAYS={retention_days}")
	print(f"MATCHED={stats['matched_before']}")
	print(f"DELETED={stats['deleted']}")
	print(f"KEPT_IMPORT_FLAG={stats['kept_import_flag']}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
