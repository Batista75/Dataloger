"""Database backup and raw-measurement retention."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.core.config import Settings
from src.core.quality_flags import QUALITY_IMPORTED_DAILY, QUALITY_LIVE, QUALITY_RAW, QUALITY_SUSPECT
from src.db.repository import MeasurementRepository

PURGE_QUALITY_FLAGS = (QUALITY_RAW, QUALITY_LIVE, QUALITY_SUSPECT)


def backup_database(db_path: Path, backup_dir: Path) -> Path:
	backup_dir.mkdir(parents=True, exist_ok=True)
	stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
	backup_path = backup_dir / f"{db_path.stem}_backup_{stamp}{db_path.suffix}"
	with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as backup:
		source.backup(backup)
	return backup_path


def prune_old_backups(backup_dir: Path, keep_count: int) -> list[Path]:
	if keep_count < 1:
		return []
	files = sorted(
		backup_dir.glob("*_backup_*.db"),
		key=lambda p: p.stat().st_mtime,
		reverse=True,
	)
	removed: list[Path] = []
	for path in files[keep_count:]:
		path.unlink(missing_ok=True)
		removed.append(path)
	return removed


def purge_cutoff_utc(settings: Settings, now: datetime | None = None) -> datetime:
	now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
	return now - timedelta(days=max(1, settings.raw_retention_days))


def run_retention_purge(repo: MeasurementRepository, settings: Settings, now: datetime | None = None) -> dict[str, int]:
	cutoff = purge_cutoff_utc(settings, now)
	cutoff_iso = cutoff.isoformat()
	before = repo.count_measurements_before(cutoff_iso, quality_flags=PURGE_QUALITY_FLAGS)
	deleted = repo.purge_measurements_before(cutoff_iso, quality_flags=PURGE_QUALITY_FLAGS)
	return {
		"cutoff_ts_utc": cutoff_iso,
		"matched_before": before,
		"deleted": deleted,
		"kept_import_flag": QUALITY_IMPORTED_DAILY,
	}
