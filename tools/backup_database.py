#!/usr/bin/env python3
"""Backup SQLite database (sqlite3 backup API) and prune old copies."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
	sys.path.insert(0, str(ROOT))

from src.core.config import settings  # noqa: E402
from src.core.maintenance import backup_database, prune_old_backups  # noqa: E402


def main() -> int:
	parser = argparse.ArgumentParser(description="Backup measurements SQLite DB.")
	parser.add_argument("--db", default=None, help="Override DB_PATH")
	parser.add_argument("--backup-dir", default=None, help="Override BACKUP_DIR")
	parser.add_argument("--keep", type=int, default=None, help="Override BACKUP_KEEP_COUNT")
	args = parser.parse_args()

	db_path = Path(args.db or settings.db_path)
	if not db_path.exists():
		print(f"DB_NOT_FOUND={db_path}")
		return 1

	backup_dir = Path(args.backup_dir or settings.backup_dir)
	keep = args.keep if args.keep is not None else settings.backup_keep_count

	backup_path = backup_database(db_path, backup_dir)
	removed = prune_old_backups(backup_dir, keep)

	print(f"BACKUP={backup_path.resolve()}")
	print(f"REMOVED_OLD={len(removed)}")
	for path in removed:
		print(f"  - {path.name}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
