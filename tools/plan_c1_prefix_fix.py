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
    eq_bak = eq_neg_bak = other = 0
    fixes = []
    for ts, live_w in rows:
        bak_row = c2.execute(
            "SELECT c1_power_w FROM measurements WHERE ts_utc = ?",
            (ts,),
        ).fetchone()
        if not bak_row:
            continue
        b = float(bak_row[0])
        if abs(live_w - b) < 0.05:
            eq_bak += 1
        elif abs(live_w + b) < 0.05:
            eq_neg_bak += 1
        else:
            other += 1
        # desired: inverted probe correction = negate raw backup
        desired = -b
        if abs(live_w - desired) > 0.05:
            fixes.append((ts, live_w, desired))
    print(f"eq_bak={eq_bak} eq_neg_bak={eq_neg_bak} other={other} need_fix={len(fixes)}")
    if fixes:
        print("first fixes:")
        for item in fixes[:5]:
            print(item[0], f"live={item[1]:+.1f}", f"want={item[2]:+.1f}")
        print("last fixes:")
        for item in fixes[-5:]:
            print(item[0], f"live={item[1]:+.1f}", f"want={item[2]:+.1f}")
