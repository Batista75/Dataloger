#!/usr/bin/env python3
import sqlite3
import sys

db = sys.argv[1]
samples = [
    "2026-06-29T00:30:00+00:00",
    "2026-06-29T06:00:00+00:00",
    "2026-06-29T10:30:00+00:00",
    "2026-06-29T11:05:00+00:00",
    "2026-06-29T11:10:00+00:00",
]
with sqlite3.connect(db) as c:
    for ts in samples:
        row = c.execute(
            """
            SELECT ts_utc, c1_power_w FROM measurements
            WHERE ts_utc >= ? ORDER BY ts_utc ASC LIMIT 1
            """,
            (ts,),
        ).fetchone()
        if row:
            print(row[0], f"{row[1]:+.1f}")
