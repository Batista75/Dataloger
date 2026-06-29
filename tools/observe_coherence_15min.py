#!/usr/bin/env python3
"""Observe real-time power coherence for 15 minutes (C1 probe check)."""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev

API_BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
DURATION_S = int(sys.argv[2]) if len(sys.argv) > 2 else 900
INTERVAL_S = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
CHANNELS = ("c1", "a2", "b2", "c2")


def fetch_latest() -> dict | None:
    try:
        with urllib.request.urlopen(f"{API_BASE}/api/measurements/latest", timeout=10) as resp:
            return json.load(resp)
    except Exception as exc:
        print(f"  [erreur] {exc}")
        return None


def autre(c1: float, a2: float, b2: float, c2: float) -> float:
    return c1 - (a2 + b2 + c2)


def main() -> int:
    out_dir = Path("/tmp") if sys.platform != "win32" else Path(".")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"observe_coherence_{stamp}.csv"
    rows: list[dict] = []

    print(f"=== Observation coherence {DURATION_S}s ===")
    print(f"API: {API_BASE}")
    print(f"Intervalle: {INTERVAL_S}s")
    print(f"CSV: {csv_path}")
    print(f"Debut UTC: {datetime.now(timezone.utc).isoformat()}")
    print("ts_utc,c1_w,a2_w,b2_w,c2_w,autre_w,c1_sign_ok")
    print("-" * 72)

    start = time.monotonic()
    end = start + DURATION_S
    sample_n = 0

    with csv_path.open("w", encoding="utf-8") as f:
        f.write("ts_utc,c1_w,a2_w,b2_w,c2_w,autre_w,voltage_v\n")
        while time.monotonic() < end:
            payload = fetch_latest()
            if payload:
                ch = payload.get("channels_power_w") or {}
                data = payload.get("data") or {}
                ts = data.get("ts_utc", "")
                vals = {k: float(ch.get(k) or 0.0) for k in CHANNELS}
                other = autre(vals["c1"], vals["a2"], vals["b2"], vals["c2"])
                row = {
                    "ts_utc": ts,
                    **{f"{k}_w": vals[k] for k in CHANNELS},
                    "autre_w": other,
                    "voltage_v": data.get("voltage_v"),
                }
                rows.append(row)
                sample_n += 1
                f.write(
                    f"{ts},{vals['c1']:.3f},{vals['a2']:.3f},{vals['b2']:.3f},"
                    f"{vals['c2']:.3f},{other:.3f},{data.get('voltage_v', '')}\n"
                )
                f.flush()
                if sample_n <= 3 or sample_n % 20 == 0:
                    print(
                        f"{ts[:19]}  C1={vals['c1']:+.0f}  A2={vals['a2']:+.0f}  "
                        f"B2={vals['b2']:+.0f}  C2={vals['c2']:+.0f}  Autre={other:+.0f}"
                    )

            sleep_left = INTERVAL_S - (time.monotonic() - start) % INTERVAL_S
            time.sleep(max(0.5, min(INTERVAL_S, sleep_left)))
            if time.monotonic() >= end:
                break

    print("-" * 72)
    print(f"Fin UTC: {datetime.now(timezone.utc).isoformat()}")
    print(f"Echantillons: {sample_n}")

    if not rows:
        print("Aucune mesure collectee.")
        return 1

    for key in CHANNELS:
        values = [r[f"{key}_w"] for r in rows]
        print(
            f"  {key.upper()}: min={min(values):+.1f}  max={max(values):+.1f}  "
            f"moy={mean(values):+.1f}  ecart-type={pstdev(values):.1f}"
        )

    autre_vals = [r["autre_w"] for r in rows]
    print(
        f"  Autre: min={min(autre_vals):+.1f}  max={max(autre_vals):+.1f}  "
        f"moy={mean(autre_vals):+.1f}  ecart-type={pstdev(autre_vals):.1f}"
    )

    c1_vals = [r["c1_w"] for r in rows]
    pos = sum(1 for v in c1_vals if v > 50)
    neg = sum(1 for v in c1_vals if v < -50)
    near0 = len(c1_vals) - pos - neg
    print(f"\nC1 signe (seuil 50 W): positif={pos}  negatif={neg}  proche_zero={near0}")
    if pos > neg * 3:
        print("  -> C1 majoritairement POSITIF (soutirage reseau) — coherent si vous importez.")
    elif neg > pos * 3:
        print("  -> C1 majoritairement NEGATIF (export) — coherent si surplus PV.")
    else:
        print("  -> C1 mixte ou faible — verifier conditions maison / PV.")

    print(f"\nFichier brut: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
