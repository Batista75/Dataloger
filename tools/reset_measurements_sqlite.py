from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset measurements table without app dependencies")
    parser.add_argument("--db", default="data/measurements.db", help="SQLite DB path")
    parser.add_argument("--include-events", action="store_true", help="Also delete system_events")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"DB_NOT_FOUND={db_path}")
        return 1

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    m_count = cur.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
    cur.execute("DELETE FROM measurements")
    try:
        cur.execute("DELETE FROM sqlite_sequence WHERE name='measurements'")
    except sqlite3.OperationalError:
        pass

    e_count = 0
    if args.include_events:
        e_count = cur.execute("SELECT COUNT(*) FROM system_events").fetchone()[0]
        cur.execute("DELETE FROM system_events")
        try:
            cur.execute("DELETE FROM sqlite_sequence WHERE name='system_events'")
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()

    print(f"DELETED_MEASUREMENTS={m_count}")
    if args.include_events:
        print(f"DELETED_SYSTEM_EVENTS={e_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
