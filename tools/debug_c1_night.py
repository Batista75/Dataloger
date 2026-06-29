#!/usr/bin/env python3
import sqlite3
from datetime import datetime

bak = "/home/mb/datalogger/data/measurements.db.bak_c1_invert_20260629_113404"
invert_until = datetime.fromisoformat("2026-06-29T11:01:28+00:00")


def signed_w_from_indices(prev_cons, prev_prod, cur_cons, cur_prod, delta_seconds):
    if delta_seconds <= 0 or delta_seconds > 900:
        return None
    d_cons = cur_cons - prev_cons
    d_prod = cur_prod - prev_prod
    if d_cons < -1e-9 or d_prod < -1e-9:
        return None
    if d_cons > 0 and d_prod > 0:
        delta_kwh = d_cons - d_prod
    elif d_cons > 0:
        delta_kwh = d_cons
    elif d_prod > 0:
        delta_kwh = -d_prod
    else:
        delta_kwh = 0.0
    return (delta_kwh * 3_600_000.0) / delta_seconds


with sqlite3.connect(bak) as c:
    rows = c.execute(
        """
        SELECT ts_utc, c1_consumption_kwh, c1_production_kwh
        FROM measurements
        WHERE ts_utc >= '2026-06-29T00:29:00+00:00' AND ts_utc <= '2026-06-29T00:31:00+00:00'
        ORDER BY ts_utc ASC
        """
    ).fetchall()
    prev = c.execute(
        """
        SELECT ts_utc, c1_consumption_kwh, c1_production_kwh
        FROM measurements WHERE ts_utc < '2026-06-29T00:29:00+00:00'
        ORDER BY ts_utc DESC LIMIT 1
        """
    ).fetchone()
    print("prev", prev)
    for i, row in enumerate(rows):
        if i == 0 and prev:
            p_ts = datetime.fromisoformat(prev[0])
            c_ts = datetime.fromisoformat(row[0])
            d = (c_ts - p_ts).total_seconds()
            w = signed_w_from_indices(prev[1], prev[2], row[1], row[2], d)
            print(row[0], "derived", w, "corrected", -w if c_ts < invert_until else w)
