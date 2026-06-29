#!/usr/bin/env python3
"""Backfill power_slots table from trusted raw measurements."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
	sys.path.insert(0, str(ROOT))

from src.core.config import settings  # noqa: E402
from src.core.power_slots import backfill_power_slots_for_day  # noqa: E402
from src.db.init_db import init_database  # noqa: E402
from src.db.repository import MeasurementRepository  # noqa: E402


def main() -> int:
	parser = argparse.ArgumentParser(description="Backfill 15-min power_slots for today.")
	parser.add_argument("--db", default=str(settings.db_path))
	args = parser.parse_args()

	db_path = Path(args.db)
	init_database(db_path)
	repo = MeasurementRepository(db_path)
	committed = backfill_power_slots_for_day(repo, settings)
	print(f"power_slots ecrits: {committed}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
