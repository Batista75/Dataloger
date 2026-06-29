#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.parse
import urllib.request

url = (
    "http://127.0.0.1:8000/api/measurements/chart-power?"
    + urllib.parse.urlencode({"from_ts_utc": "2026-06-28T22:00:00+00:00"})
)
with urllib.request.urlopen(url, timeout=60) as resp:
    payload = json.load(resp)

slots = payload.get("data") or []
filled = sum(1 for slot in slots if slot.get("c1_signed_w") is not None)
print(f"sample_count={payload.get('sample_count')}")
print(f"slots_with_c1={filled}/{len(slots)}")
if filled:
    last = [slot for slot in slots if slot.get("c1_signed_w") is not None][-1]
    print(f"last_c1_slot={last['ts_utc'][:19]} c1_w={last['c1_signed_w']}")
