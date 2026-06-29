#!/usr/bin/env python3
import csv
import sys
from statistics import mean, pstdev

path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/observe_coherence_20260629_131052.csv"
rows = list(csv.DictReader(open(path, encoding="utf-8")))
print(f"samples={len(rows)}")
if not rows:
    raise SystemExit(0)
for key in ("c1_w", "a2_w", "b2_w", "c2_w", "autre_w"):
    vals = [float(r[key]) for r in rows]
    print(
        f"{key}: min={min(vals):+.1f} max={max(vals):+.1f} "
        f"avg={mean(vals):+.1f} std={pstdev(vals):.1f}"
    )
c1 = [float(r["c1_w"]) for r in rows]
print(f"C1_pos={sum(1 for x in c1 if x > 50)} C1_neg={sum(1 for x in c1 if x < -50)}")
print(f"first={rows[0]['ts_utc'][:19]} last={rows[-1]['ts_utc'][:19]}")
