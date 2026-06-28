from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

CONSUMPTION_FIELDS = (
    "a1_consumption_kwh",
    "b1_consumption_kwh",
    "c1_consumption_kwh",
    "a2_consumption_kwh",
    "b2_consumption_kwh",
    "c2_consumption_kwh",
    "total_consumption_kwh",
)


def create_backup(db_path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_suffix(db_path.suffix + f".bak_pre_switch_{stamp}")
    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as backup:
        source.backup(backup)
    return backup_path


def zero_consumption_before_cutoff(db_path: Path, day_iso: str, cutoff_ts_utc: str) -> tuple[int, int]:
    day_start = f"{day_iso}T00:00:00+00:00"
    set_clause = ", ".join(f"{field}=0" for field in CONSUMPTION_FIELDS)

    with sqlite3.connect(db_path) as conn:
        total_before = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM measurements
                WHERE ts_utc >= ? AND ts_utc < ?
                """,
                (day_start, cutoff_ts_utc),
            ).fetchone()[0]
        )

        conn.execute(
            f"""
            UPDATE measurements
            SET {set_clause}
            WHERE ts_utc >= ? AND ts_utc < ?
            """,
            (day_start, cutoff_ts_utc),
        )
        conn.commit()

        zeroed_after = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM measurements
                WHERE ts_utc >= ? AND ts_utc < ?
                  AND total_consumption_kwh = 0
                """,
                (day_start, cutoff_ts_utc),
            ).fetchone()[0]
        )

    return total_before, zeroed_after


def main() -> int:
    parser = argparse.ArgumentParser(description="Zero consumption values before a switch cutoff timestamp.")
    parser.add_argument("--db", required=True, help="Path to measurements.db")
    parser.add_argument("--day", required=True, help="Target UTC day in YYYY-MM-DD")
    parser.add_argument("--cutoff-ts-utc", required=True, help="Cutoff timestamp in UTC (ISO format)")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    backup_path = create_backup(db_path)
    touched, zeroed = zero_consumption_before_cutoff(db_path, args.day, args.cutoff_ts_utc)

    print(f"Backup: {backup_path}")
    print(f"Rows in window: {touched}")
    print(f"Rows zeroed: {zeroed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
