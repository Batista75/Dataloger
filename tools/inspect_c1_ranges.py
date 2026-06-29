#!/usr/bin/env python3
import sqlite3
import sys

db = sys.argv[1] if len(sys.argv) > 1 else "data/measurements.db"
cut = sys.argv[2] if len(sys.argv) > 2 else "2026-06-29T11:10:52+00:00"
with sqlite3.connect(db) as c:
    for label, sql, params in (
        ("pre", "ts_utc < ?", (cut,)),
        ("post", "ts_utc >= ?", (cut,)),
    ):
        r = c.execute(
            f"""
            SELECT COUNT(*), ROUND(AVG(c1_power_w),1), ROUND(MIN(c1_power_w),1), ROUND(MAX(c1_power_w),1),
                SUM(CASE WHEN c1_power_w > 50 THEN 1 ELSE 0 END),
                SUM(CASE WHEN c1_power_w < -50 THEN 1 ELSE 0 END)
            FROM measurements WHERE {sql} AND c1_power_w IS NOT NULL
            """,
            params,
        ).fetchone()
        print(label, r)
