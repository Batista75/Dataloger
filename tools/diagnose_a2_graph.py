#!/usr/bin/env python3
import json
import sqlite3
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo
from datetime import datetime

DB = "/home/mb/datalogger/data/measurements.db"
DAY = "2026-06-28T22:00:00+00:00"

url = "http://127.0.0.1:8000/api/measurements/chart-power?" + urllib.parse.urlencode(
    {"from_ts_utc": DAY}
)
with urllib.request.urlopen(url, timeout=120) as r:
    chart = json.load(r)

slots = chart["data"]
a2_filled = [s for s in slots if s.get("a2_signed_w") is not None]
print(f"chart_samples={chart['sample_count']} a2_slots={len(a2_filled)}/96")
if a2_filled:
    print(f"first_a2 slot={a2_filled[0]['slot_index']} ts={a2_filled[0]['ts_utc'][:19]} w={a2_filled[0]['a2_signed_w']}")
    print(f"last_a2 slot={a2_filled[-1]['slot_index']} ts={a2_filled[-1]['ts_utc'][:19]} w={a2_filled[-1]['a2_signed_w']}")

# slots with only c1 but no a2
c1_only = [s for s in slots if s.get("c1_signed_w") is not None and s.get("a2_signed_w") is None]
a2_only = [s for s in slots if s.get("a2_signed_w") is not None and s.get("c1_signed_w") is None]
print(f"c1_without_a2={len(c1_only)} a2_without_c1={len(a2_only)}")
if c1_only[:3]:
    for s in c1_only[:3]:
        print(f"  c1_only slot={s['slot_index']} {s['ts_utc'][:19]}")
if a2_only[:3]:
    for s in a2_only[:3]:
        print(f"  a2_only slot={s['slot_index']} {s['ts_utc'][:19]} a2={s['a2_signed_w']}")

conn = sqlite3.connect(DB)
row = conn.execute(
    "SELECT MIN(ts_utc), MAX(ts_utc), COUNT(*), "
    "SUM(CASE WHEN a2_power_w IS NOT NULL THEN 1 ELSE 0 END), "
    "SUM(CASE WHEN c1_power_w IS NOT NULL THEN 1 ELSE 0 END) "
    "FROM measurements WHERE ts_utc >= ?",
    (DAY,),
).fetchone()
print(f"db min={row[0]} max={row[1]} count={row[2]} a2_pw={row[3]} c1_pw={row[4]}")

# first rows with a2_power_w
rows = conn.execute(
    "SELECT ts_utc, a2_power_w, c1_power_w FROM measurements "
    "WHERE ts_utc >= ? AND a2_power_w IS NOT NULL ORDER BY ts_utc ASC LIMIT 3",
    (DAY,),
).fetchall()
for r in rows:
    print(f"  db_first_a2 {r[0][:19]} a2={r[1]} c1={r[2]}")

now_paris = datetime.now(ZoneInfo("Europe/Paris"))
slot_idx = (now_paris.hour * 60 + now_paris.minute) // 15
print(f"now_paris={now_paris.strftime('%H:%M')} visible_last_slot={slot_idx}")

for idx in list(range(0, 10)) + [31, 40, 48, 52, 53, 54]:
    s = slots[idx]
    print(
        f"slot[{idx}] {s['ts_utc'][11:16]} paris~+2h  "
        f"a2={s.get('a2_signed_w')} c1={s.get('c1_signed_w')}"
    )
