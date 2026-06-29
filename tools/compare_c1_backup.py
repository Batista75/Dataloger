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
        ORDER BY ts_utc DESC LIMIT 6
        """,
        (cut,),
    ).fetchall()
    print("compare pre-fix (live vs backup before scripts):")
    for ts, live_w in rows:
        bak_w = c2.execute(
            "SELECT c1_power_w FROM measurements WHERE ts_utc = ?",
            (ts,),
        ).fetchone()
        b = bak_w[0] if bak_w else None
        print(ts, f"live={live_w:+.1f}", f"bak={b:+.1f}" if b is not None else "bak=None")
