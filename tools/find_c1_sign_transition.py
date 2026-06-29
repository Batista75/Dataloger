#!/usr/bin/env python3
import sqlite3
import sys

bak = sys.argv[1]
cut = "2026-06-29T11:10:52+00:00"
with sqlite3.connect(bak) as c:
    rows = c.execute(
        """
        SELECT ts_utc, c1_power_w FROM measurements
        WHERE c1_power_w IS NOT NULL AND ts_utc < ?
        ORDER BY ts_utc ASC
        """,
        (cut,),
    ).fetchall()
    pos = neg = 0
    last_pos_ts = None
    first_neg_ts = None
    for ts, w in rows:
        if w > 50:
            pos += 1
            last_pos_ts = ts
        elif w < -50:
            neg += 1
            if first_neg_ts is None:
                first_neg_ts = ts
    print(f"rows={len(rows)} pos={pos} neg={neg}")
    print("last_pos_ts", last_pos_ts)
    print("first_neg_ts", first_neg_ts)
    if first_neg_ts:
        for ts, w in rows:
            if ts >= first_neg_ts:
                print("transition", ts, f"{w:+.1f}")
                break
