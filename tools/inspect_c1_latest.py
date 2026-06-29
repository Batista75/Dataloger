#!/usr/bin/env python3
import sqlite3
import sys

db = sys.argv[1]
with sqlite3.connect(db) as c:
    print("latest:")
    for r in c.execute(
        "SELECT ts_utc, c1_power_w FROM measurements WHERE c1_power_w IS NOT NULL ORDER BY ts_utc DESC LIMIT 5"
    ):
        print(r[0], f"{r[1]:+.1f}")
