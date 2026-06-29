#!/usr/bin/env python3
import json
import urllib.parse
import urllib.request

url = (
    "http://127.0.0.1:8000/api/measurements/chart-power?"
    + urllib.parse.urlencode({"from_ts_utc": "2026-06-28T22:00:00+00:00"})
)
with urllib.request.urlopen(url, timeout=120) as resp:
    payload = json.load(resp)
for idx in [0, 31, 48]:
    s = payload["data"][idx]
    print(idx, repr(s["ts_utc"]), s.get("c1_signed_w"))
