#!/usr/bin/env python3
"""Compare latest real-time power vs last chart-power slots."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")


def paris_day_start_utc() -> str:
    now = datetime.now(PARIS)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    return day_start.isoformat()


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.load(resp)


def main() -> None:
    latest = get_json("http://127.0.0.1:8000/api/measurements/latest")
    channels = latest.get("channels_power_w") or {}
    data = latest.get("data") or {}
    print("=== Temps reel (channels_power_w) ===")
    for ch in ("c1", "a2", "b2", "c2"):
        print(f"  {ch}: {channels.get(ch)} W  (ts={data.get('ts_utc', '')[:19]})")

    day_start = paris_day_start_utc()
    chart_url = (
        "http://127.0.0.1:8000/api/measurements/chart-power?"
        + urllib.parse.urlencode({"from_ts_utc": day_start, "slot_minutes": 15})
    )
    chart = get_json(chart_url)
    slots = chart.get("data") or []

    filled = [s for s in slots if s.get("c1_signed_w") is not None]
    print(f"\n=== Graphe (chart-power, {len(filled)} creneaux C1) ===")
    for s in filled[-5:]:
        idx = s.get("slot_index")
        ts = s.get("ts_utc", "")[:19]
        print(
            f"  slot[{idx}] {ts}  "
            f"C1={s.get('c1_signed_w')}  A2={s.get('a2_signed_w')}  "
            f"B2={s.get('b2_signed_w')}  C2={s.get('c2_signed_w')}"
        )

    if not filled:
        print("  (aucun creneau)")
        return

    last = filled[-1]
    print("\n=== Ecart dernier creneau vs temps reel ===")
    for ch in ("c1", "a2", "b2", "c2"):
        rt = float(channels.get(ch) or 0)
        gr = float(last.get(f"{ch}_signed_w") or 0)
        diff = gr - rt
        pct = (diff / rt * 100) if abs(rt) >= 1 else None
        pct_s = f" ({pct:+.1f}%)" if pct is not None else ""
        print(f"  {ch}: graphe={gr:.1f} W  temps_reel={rt:.1f} W  delta={diff:+.1f} W{pct_s}")

    # Last 3 raw DB rows with power_w
    m_url2 = "http://127.0.0.1:8000/api/measurements?minutes=5&limit=5"
    recent = get_json(m_url2).get("data") or []
    if recent:
        print("\n=== 5 dernieres lignes DB (power_w) ===")
        for row in recent[-3:]:
            ts = row.get("ts_utc", "")[:19]
            parts = [f"{ch}={row.get(ch + '_power_w')}" for ch in ("c1", "a2", "b2", "c2")]
            print(f"  {ts}  {' '.join(parts)}")

    # Moyenne DB sur le creneau 15 min en cours
    now_paris = datetime.now(PARIS)
    slot_min = (now_paris.hour * 60 + now_paris.minute) // 15 * 15
    slot_start_paris = now_paris.replace(hour=slot_min // 60, minute=slot_min % 60, second=0, microsecond=0)
    slot_start_utc = slot_start_paris.astimezone(timezone.utc)
    slot_idx = int((slot_start_utc.timestamp() - datetime.fromisoformat(day_start).timestamp()) // 900)
    current_slot = next((s for s in slots if s.get("slot_index") == slot_idx), None)
    if current_slot:
        print(f"\n=== Creneau courant slot[{slot_idx}] ({current_slot.get('ts_utc','')[:19]}) ===")
        for ch in ("c1", "a2", "b2", "c2"):
            print(f"  {ch}: graphe_moyenne={current_slot.get(ch + '_signed_w')} W")


if __name__ == "__main__":
    main()
