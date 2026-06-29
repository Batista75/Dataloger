#!/usr/bin/env python3
import sqlite3
import sys

db = sys.argv[1]
cut = sys.argv[2] if len(sys.argv) > 2 else "2026-06-29T11:10:52+00:00"
with sqlite3.connect(db) as c:
    print("=== 5 avant ===")
    for r in c.execute(
        """
        SELECT ts_utc, c1_power_w FROM measurements
        WHERE c1_power_w IS NOT NULL AND ts_utc < ?
        ORDER BY ts_utc DESC LIMIT 5
        """,
        (cut,),
    ).fetchall()[::-1]:
        print(r[0], f"{r[1]:+.1f}")
    print("=== 5 apres ===")
    for r in c.execute(
        """
        SELECT ts_utc, c1_power_w FROM measurements
        WHERE c1_power_w IS NOT NULL AND ts_utc >= ?
        ORDER BY ts_utc ASC LIMIT 5
        """,
        (cut,),
    ).fetchall():
        print(r[0], f"{r[1]:+.1f}")
