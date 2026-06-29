#!/usr/bin/env python3
"""Mark unreliable live measurements as quality_flag=3 (suspect)."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
	sys.path.insert(0, str(ROOT))

from src.core.config import settings  # noqa: E402
from src.db.repository import MeasurementRepository  # noqa: E402


def create_backup(db_path: Path) -> Path:
	from datetime import datetime, timezone

	stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
	backup_path = db_path.with_suffix(db_path.suffix + f".bak_quality3_{stamp}")
	with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as backup:
		source.backup(backup)
	return backup_path


def main() -> int:
	parser = argparse.ArgumentParser(description="Mark suspect measurements (quality_flag=3).")
	parser.add_argument("--db", default="data/measurements.db")
	parser.add_argument("--dry-run", action="store_true")
	args = parser.parse_args()

	db_path = Path(args.db)
	if not db_path.exists():
		raise FileNotFoundError(db_path)

	repo = MeasurementRepository(db_path)
	if args.dry_run:
		with sqlite3.connect(db_path) as conn:
			count = conn.execute(
				"""
				SELECT COUNT(*) FROM measurements
				WHERE quality_flag = 1 AND ts_utc >= ? AND ts_utc < ?
				""",
				(f"{settings.chart_unreliable_from}T00:00:00+00:00", f"{settings.chart_unreliable_until}T23:59:59+00:00"),
			).fetchone()[0]
		print(f"dry-run candidates (live in range): {count}")
		return 0

	backup = create_backup(db_path)
	print(f"Sauvegarde: {backup}")
	updated = repo.mark_suspect_measurements_before_trusted_cutoff(
		settings.chart_unreliable_from,
		settings.chart_unreliable_until,
		settings.chart_unreliable_local_start,
	)
	print(f"quality_flag=3 applique sur {updated} lignes")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
