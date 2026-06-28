"""One-shot Refoss RPC snapshot for mobile app comparison."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from requests.auth import HTTPDigestAuth

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

CHANNEL_BY_ID = {1: "a1", 2: "b1", 3: "c1", 4: "a2", 5: "b2", 6: "c2"}
CHANNEL_LABELS = {
    "a1": "Canal A1",
    "b1": "Canal B1",
    "c1": "Canal C1 (EDF total par defaut UI)",
    "a2": "Canal A2 (generateur par defaut UI)",
    "b2": "Canal B2",
    "c2": "Canal C2",
}


def fetch_status(url_base: str, auth: HTTPDigestAuth | None, params: dict) -> dict:
    response = requests.get(
        f"{url_base.rstrip('/')}/rpc/Em.Status.Get",
        params=params,
        timeout=5,
        auth=auth,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("RPC payload is not an object")
    return payload


def extract_entries(payload: dict) -> list[dict]:
    root = payload.get("result", payload)
    if not isinstance(root, dict):
        return []
    status = root.get("status")
    if isinstance(status, list):
        return [item for item in status if isinstance(item, dict)]
    return []


def main() -> int:
    url_base = os.getenv("EM06_HTTP_URL", "http://192.168.1.119")
    username = os.getenv("EM06_HTTP_USERNAME", os.getenv("ADMIN_USERNAME", "admin"))
    password = os.getenv("EM06_HTTP_PASSWORD", os.getenv("ADMIN_PASSWORD", ""))
    auth = HTTPDigestAuth(username, password) if password else None

    snapshot_utc = datetime.now(timezone.utc)
    payload = fetch_status(url_base, auth, {"id": 65535})
    entries = extract_entries(payload)

    rows: list[dict] = []
    total_w = 0.0
    for entry in entries:
        channel_id = int(float(entry.get("id") or 0))
        channel = CHANNEL_BY_ID.get(channel_id)
        if not channel:
            continue
        power_w = float(entry.get("power") or 0.0)
        total_w += power_w
        rows.append(
            {
                "channel": channel,
                "channel_id": channel_id,
                "label": CHANNEL_LABELS.get(channel, channel),
                "power_w": round(power_w, 1),
                "voltage_v": entry.get("voltage"),
                "pf": entry.get("pf"),
            }
        )

    output = {
        "snapshot_utc": snapshot_utc.isoformat(),
        "snapshot_local": snapshot_utc.astimezone().isoformat(),
        "source": "refoss_local_rpc",
        "device_url": url_base,
        "rpc_method": "Em.Status.Get",
        "rpc_params": {"id": 65535},
        "channels": sorted(rows, key=lambda item: item["channel_id"]),
        "total_signed_w": round(total_w, 1),
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
