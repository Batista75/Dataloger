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
        WHERE c1_power_w IS NOT NULL AND ts_utc >= ?
        ORDER BY ts_utc ASC
        """,
        (cut,),
    ).fetchall()
    neg_flip = same = other = 0
    for ts, live_w in rows:
        b = c2.execute(
            "SELECT c1_power_w FROM measurements WHERE ts_utc = ?",
            (ts,),
        ).fetchone()
        if not b:
            continue
        b = float(b[0])
        if abs(live_w + b) < 0.05:
            neg_flip += 1
        elif abs(live_w - b) < 0.05:
            same += 1
        else:
            other += 1
    print(f"post-cut rows={len(rows)} flipped={neg_flip} same={same} other={other}")
