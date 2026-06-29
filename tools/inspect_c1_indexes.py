#!/usr/bin/env python3
import sqlite3
import sys

db = sys.argv[1]
day = "2026-06-28T22:00:00+00:00"
first_pw = "2026-06-29T10:08:12+00:00"
cut = "2026-06-29T11:10:52+00:00"
with sqlite3.connect(db) as c:
    r0 = c.execute(
        "SELECT MIN(ts_utc), COUNT(*) FROM measurements WHERE c1_power_w IS NOT NULL"
    ).fetchone()
    print("first c1_power_w", r0)
    n = c.execute(
        "SELECT COUNT(*) FROM measurements WHERE ts_utc >= ? AND ts_utc < ?",
        (day, first_pw),
    ).fetchone()[0]
    print("rows before first c1_power_w:", n)
    r = c.execute(
        """
        SELECT MIN(c1_consumption_kwh), MAX(c1_consumption_kwh),
            MIN(c1_production_kwh), MAX(c1_production_kwh)
        FROM measurements WHERE ts_utc >= ? AND ts_utc < ?
        """,
        (day, cut),
    ).fetchone()
    print("pre-cut c1 index range cons", r[0], r[1], "prod", r[2], r[3])
    r2 = c.execute(
        """
        SELECT MIN(c1_consumption_kwh), MAX(c1_consumption_kwh),
            MIN(c1_production_kwh), MAX(c1_production_kwh)
        FROM measurements WHERE ts_utc >= ? AND ts_utc < ?
        """,
        (day, first_pw),
    ).fetchone()
    print("before power_w c1 index range cons", r2[0], r2[1], "prod", r2[2], r2[3])
