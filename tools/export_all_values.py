from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path


def export_table(conn: sqlite3.Connection, table: str, out_csv: Path) -> int:
    cur = conn.cursor()
    rows = cur.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
    if not rows:
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        out_csv.write_text("", encoding="utf-8")
        return 0

    columns = [d[0] for d in cur.description]
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export all SQLite values to CSV")
    parser.add_argument("--db", default="data/measurements.db", help="Path to SQLite DB")
    parser.add_argument("--out-measurements", default="exports/measurements_all.csv", help="Output CSV for measurements")
    parser.add_argument("--out-events", default="exports/system_events_all.csv", help="Output CSV for system events")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"DB_NOT_FOUND={db_path}")
        return 1

    conn = sqlite3.connect(db_path)
    try:
        m_count = export_table(conn, "measurements", Path(args.out_measurements))
        e_count = export_table(conn, "system_events", Path(args.out_events))
        print(f"MEASUREMENTS_COUNT={m_count}")
        print(f"SYSTEM_EVENTS_COUNT={e_count}")
        print(f"MEASUREMENTS_CSV={args.out_measurements}")
        print(f"SYSTEM_EVENTS_CSV={args.out_events}")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
