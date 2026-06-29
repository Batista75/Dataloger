#!/usr/bin/env python3
"""Daily maintenance: backup DB then purge raw measurements past retention."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
	sys.path.insert(0, str(ROOT))

from src.core.config import settings  # noqa: E402
from src.core.maintenance import backup_database, prune_old_backups, run_retention_purge  # noqa: E402
from src.db.repository import MeasurementRepository  # noqa: E402


def main() -> int:
	parser = argparse.ArgumentParser(description="Backup + purge raw measurements (retention).")
	parser.add_argument("--db", default=None)
	parser.add_argument("--skip-backup", action="store_true")
	parser.add_argument("--skip-purge", action="store_true")
	args = parser.parse_args()

	db_path = Path(args.db or settings.db_path)
	if not db_path.exists():
		print(f"DB_NOT_FOUND={db_path}")
		return 1

	if not args.skip_backup:
		backup_path = backup_database(db_path, settings.backup_dir)
		removed = prune_old_backups(settings.backup_dir, settings.backup_keep_count)
		print(f"BACKUP={backup_path.resolve()}")
		print(f"BACKUPS_PRUNED={len(removed)}")

	if not args.skip_purge:
		repo = MeasurementRepository(db_path)
		stats = run_retention_purge(repo, settings)
		print(f"CUTOFF={stats['cutoff_ts_utc']}")
		print(f"DELETED={stats['deleted']}")

	return 0


if __name__ == "__main__":
	raise SystemExit(main())
