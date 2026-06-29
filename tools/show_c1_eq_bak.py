#!/usr/bin/env python3
import sqlite3
import sys

live = sys.argv[1]
bak = sys.argv[2]
cut = "2026-06-29T11:10:52+00:00"
with sqlite3.connect(live) as c1, sqlite3.connect(bak) as c2:
    rows = c1.execute(
        """
        SELECT ts_utc, c1_power_w FROM measurements
        WHERE c1_power_w IS NOT NULL AND ts_utc < ?
        ORDER BY ts_utc ASC
        """,
        (cut,),
    ).fetchall()
    for ts, live_w in rows:
        bak_row = c2.execute(
            "SELECT c1_power_w FROM measurements WHERE ts_utc = ?",
            (ts,),
        ).fetchone()
        if not bak_row:
            continue
        b = float(bak_row[0])
        if abs(live_w - b) < 0.05:
            print(ts, f"live={live_w:+.1f}", f"bak={b:+.1f}", f"want={-b:+.1f}")
