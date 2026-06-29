#!/usr/bin/env python3
"""Diagnose chart gaps for a local-time window (Europe/Paris summer = UTC+2)."""
from __future__ import annotations

import json
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB = Path("/home/mb/datalogger/data/measurements.db")
# Local window 07:45 - 12:00 on 2026-06-29 (CEST = UTC+2)
LOCAL_DAY = "2026-06-29"
FROM_LOCAL = f"{LOCAL_DAY}T07:45:00+02:00"
TO_LOCAL = f"{LOCAL_DAY}T12:00:00+02:00"


def main() -> None:
    from_ts = datetime.fromisoformat(FROM_LOCAL).astimezone(timezone.utc)
    to_ts = datetime.fromisoformat(TO_LOCAL).astimezone(timezone.utc)
    day_start = datetime.fromisoformat(f"{LOCAL_DAY}T00:00:00+02:00").astimezone(timezone.utc)

    print(f"window_utc {from_ts.isoformat()} -> {to_ts.isoformat()}")
    print(f"day_start_utc {day_start.isoformat()}")

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT ts_utc, c1_power_w, a2_power_w
        FROM measurements
        WHERE ts_utc >= ? AND ts_utc < ?
        ORDER BY ts_utc ASC
        """,
        (from_ts.isoformat(), to_ts.isoformat()),
    ).fetchall()
    print(f"db_rows_in_window={len(rows)}")
    if rows:
        print(f"  first={rows[0]['ts_utc']} c1={rows[0]['c1_power_w']}")
        print(f"  last={rows[-1]['ts_utc']} c1={rows[-1]['c1_power_w']}")

    gaps = []
    for i in range(1, len(rows)):
        t0 = datetime.fromisoformat(rows[i - 1]["ts_utc"].replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(rows[i]["ts_utc"].replace("Z", "+00:00"))
        dt = (t1 - t0).total_seconds()
        if dt > 120:
            gaps.append((rows[i - 1]["ts_utc"], rows[i]["ts_utc"], dt))
    print(f"db_gaps_over_2min={len(gaps)}")
    for g in gaps[:5]:
        print(f"  gap {g[2]:.0f}s {g[0]} -> {g[1]}")

    url = (
        "http://127.0.0.1:8000/api/measurements/chart-power?"
        + urllib.parse.urlencode({"from_ts_utc": day_start.isoformat(), "slot_minutes": 15})
    )
    with urllib.request.urlopen(url, timeout=120) as resp:
        payload = json.load(resp)
    slots = payload.get("data") or []
    print(f"chart_sample_count={payload.get('sample_count')}")

    # slots 31-48 = 07:45 - 12:00 local (31*15min = 7h45 from midnight)
    for idx in range(31, 49):
        if idx >= len(slots):
            break
        s = slots[idx]
        c1 = s.get("c1_signed_w")
        a2 = s.get("a2_signed_w")
        print(f"  slot[{idx}] {s.get('ts_utc','')[:19]} c1={c1} a2={a2}")

    conn.close()


if __name__ == "__main__":
    main()
