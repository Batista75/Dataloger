#!/usr/bin/env python3
"""Analyze measurement gaps for today's chart data."""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def main() -> int:
    from_ts = sys.argv[1] if len(sys.argv) > 1 else "2026-06-28T22:00:00+00:00"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
    url = (
        "http://127.0.0.1:8000/api/measurements?"
        + urllib.parse.urlencode({"from_ts_utc": from_ts, "limit": limit})
    )
    with urllib.request.urlopen(url, timeout=30) as resp:
        payload = json.load(resp)
    rows = payload.get("data") or []
    print(f"count={len(rows)}")
    if not rows:
        return 0
    print(f"first={rows[0]['ts_utc']}")
    print(f"last={rows[-1]['ts_utc']}")

    gaps: list[tuple[str, str, float]] = []
    for i in range(1, len(rows)):
        t0 = datetime.fromisoformat(rows[i - 1]["ts_utc"].replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(rows[i]["ts_utc"].replace("Z", "+00:00"))
        dt = (t1 - t0).total_seconds()
        if dt > 120:
            gaps.append((rows[i - 1]["ts_utc"], rows[i]["ts_utc"], dt))

    print(f"gaps_over_2min={len(gaps)}")
    for start, end, dt in gaps[:8]:
        print(f"  gap {dt:.0f}s {start} -> {end}")

    # Sample derived C1 power from index deltas (old method)
    if len(rows) >= 2:
        prev, cur = rows[0], rows[1]
        dt = (
            datetime.fromisoformat(cur["ts_utc"].replace("Z", "+00:00"))
            - datetime.fromisoformat(prev["ts_utc"].replace("Z", "+00:00"))
        ).total_seconds()
        d_cons = float(cur["c1_consumption_kwh"]) - float(prev["c1_consumption_kwh"])
        d_prod = float(cur["c1_production_kwh"]) - float(prev["c1_production_kwh"])
        old_w = (d_cons - d_prod) * 3600000 / dt if dt > 0 else 0
        if d_cons > 0 and d_prod <= 0:
            new_w = d_cons * 3600000 / dt
        elif d_prod > 0 and d_cons <= 0:
            new_w = -d_prod * 3600000 / dt
        else:
            new_w = (d_cons - d_prod) * 3600000 / dt if dt > 0 else 0
        print(f"sample_c1_old_method_w={old_w:.1f} fixed_method_w={new_w:.1f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
