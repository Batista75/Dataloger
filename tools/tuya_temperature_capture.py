#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import inspect
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tinytuya


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_mac(value: str) -> str:
    cleaned = "".join(ch for ch in value.upper() if ch in "0123456789ABCDEF")
    if len(cleaned) != 12:
        return value.upper()
    return ":".join(cleaned[i : i + 2] for i in range(0, 12, 2))


def _split_csv_values(raw: str) -> list[str]:
    return [item.strip() for item in (raw or "").split(",") if item.strip()]


def _find_temperature_c(dps: dict[str, Any], preferred_dp: str | None) -> float | None:
    if preferred_dp and preferred_dp in dps:
        value = _to_number(dps.get(preferred_dp))
        if value is not None:
            return _normalize_temperature(value)

    # Heuristic order used by many Tuya temperature sensors.
    candidate_keys = ["1", "2", "3", "9", "18", "19", "20", "21", "22", "101", "102"]

    for key in candidate_keys:
        if key not in dps:
            continue
        value = _to_number(dps.get(key))
        if value is None:
            continue
        temp = _normalize_temperature(value)
        if temp is not None:
            return temp

    # Fallback: scan all numeric DPS values and pick one in a plausible range.
    for raw_value in dps.values():
        value = _to_number(raw_value)
        if value is None:
            continue
        temp = _normalize_temperature(value)
        if temp is not None:
            return temp

    return None


def _find_temperature_from_cloud_status(
    status_rows: list[dict[str, Any]], preferred_code: str | None
) -> tuple[float | None, str | None, Any]:
    code_map: dict[str, Any] = {}
    for row in status_rows:
        if not isinstance(row, dict):
            continue
        code = row.get("code")
        if isinstance(code, str):
            code_map[code] = row.get("value")

    if preferred_code and preferred_code in code_map:
        value = _to_number(code_map[preferred_code])
        if value is not None:
            temp = _normalize_temperature(value)
            if temp is not None:
                return temp, preferred_code, code_map[preferred_code]

    candidate_codes = [
        "va_temperature",
        "temp_current",
        "temperature",
        "temp",
        "cur_temperature",
        "cur_temp",
    ]
    for code in candidate_codes:
        value = _to_number(code_map.get(code))
        if value is None:
            continue
        temp = _normalize_temperature(value)
        if temp is not None:
            return temp, code, code_map.get(code)

    for code, raw_value in code_map.items():
        value = _to_number(raw_value)
        if value is None:
            continue
        temp = _normalize_temperature(value)
        if temp is not None:
            return temp, code, raw_value

    return None, None, None


def _normalize_temperature(value: float) -> float | None:
    # Tuya often reports temperature with x10 precision (e.g. 253 => 25.3C)
    if -500 <= value <= 800:
        if value > 120 or value < -80:
            temp = value / 10.0
        else:
            temp = value
    else:
        temp = value / 10.0

    if -60 <= temp <= 120:
        return round(temp, 2)
    return None


def _to_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _scan_devices(max_time: float = 8.0) -> list[dict[str, Any]]:
    scan_fn = tinytuya.deviceScan
    sig = inspect.signature(scan_fn)
    kwargs: dict[str, Any] = {}

    if "show_timer" in sig.parameters:
        kwargs["show_timer"] = False
    if "max_time" in sig.parameters:
        kwargs["max_time"] = max_time
    elif "maxretry" in sig.parameters:
        kwargs["maxretry"] = max(1, int(round(max_time)))
    if "verbose" in sig.parameters:
        kwargs.setdefault("verbose", False)

    scanned = scan_fn(**kwargs)
    devices: list[dict[str, Any]] = []
    if not isinstance(scanned, dict):
        return devices

    for ip, info in scanned.items():
        if not isinstance(info, dict):
            continue
        mac = _normalize_mac(str(info.get("mac", "")))
        devices.append(
            {
                "ip": ip,
                "mac": mac,
                "gwId": info.get("gwId"),
                "version": str(info.get("version", "")),
                "name": info.get("name"),
                "productKey": info.get("productKey"),
            }
        )

    return devices


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _append_csv(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "ts_utc",
        "device_id",
        "device_ip",
        "device_mac",
        "temperature_c",
        "dps_key",
        "raw_value",
        "source",
    ]
    file_exists = path.exists()

    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow({name: payload.get(name) for name in fieldnames})


def _read_device_status_local(args: argparse.Namespace) -> dict[str, Any]:
    retries = max(1, int(args.retries))
    delay_seconds = max(0.0, float(args.retry_delay_seconds))
    last_exc: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            device = tinytuya.Device(
                dev_id=args.device_id,
                address=args.ip,
                local_key=args.local_key,
                version=float(args.version),
            )
            status = device.status()
            if isinstance(status, dict):
                return status
            raise RuntimeError("TinyTuya returned a non-dict status payload")
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < retries:
                time.sleep(delay_seconds)

    raise RuntimeError(f"TinyTuya status failed after {retries} attempt(s): {last_exc}")


def _read_device_status_cloud(args: argparse.Namespace) -> dict[str, Any]:
    if not args.api_key or not args.api_secret:
        raise ValueError("Cloud mode requires --api-key and --api-secret")

    cloud = tinytuya.Cloud(
        apiRegion=str(args.api_region),
        apiKey=str(args.api_key),
        apiSecret=str(args.api_secret),
        apiDeviceID=str(args.device_id),
    )
    status = cloud.getstatus(str(args.device_id))
    if not isinstance(status, dict):
        raise RuntimeError("TinyTuya Cloud returned a non-dict status payload")
    if status.get("success") is not True:
        raise RuntimeError(f"TinyTuya Cloud status failed: {status}")
    return status


def _build_payload(args: argparse.Namespace) -> dict[str, Any]:
    selected_dp_key: str | None = None
    raw_value: Any = None
    preferred_dp = str(args.temperature_dp) if args.temperature_dp else None
    source = "local"

    mode = str(args.mode).lower()
    if mode not in {"local", "cloud", "auto"}:
        raise ValueError("--mode must be one of: local, cloud, auto")

    if mode in {"local", "auto"}:
        try:
            status = _read_device_status_local(args)
            dps = status.get("dps", {})
            if not isinstance(dps, dict):
                raise ValueError("No DPS object in TinyTuya local status")

            temp = _find_temperature_c(dps, preferred_dp)
            if temp is None:
                raise ValueError("No plausible temperature value found in DPS payload")

            selected_dp_key = preferred_dp if preferred_dp and preferred_dp in dps else None
            raw_value = dps.get(selected_dp_key) if selected_dp_key else None

            if selected_dp_key is None:
                # Best effort: infer matching key by normalized value.
                for key, value in dps.items():
                    numeric = _to_number(value)
                    if numeric is None:
                        continue
                    normalized = _normalize_temperature(numeric)
                    if normalized is not None and abs(normalized - temp) < 0.001:
                        selected_dp_key = str(key)
                        raw_value = value
                        break
        except Exception:
            if mode == "local":
                raise
            status = _read_device_status_cloud(args)
            rows = status.get("result", [])
            if not isinstance(rows, list):
                raise ValueError("No result[] array in TinyTuya cloud status")
            temp, selected_dp_key, raw_value = _find_temperature_from_cloud_status(rows, preferred_dp)
            if temp is None:
                raise ValueError("No plausible temperature value found in cloud status payload")
            source = "cloud"
    else:
        status = _read_device_status_cloud(args)
        rows = status.get("result", [])
        if not isinstance(rows, list):
            raise ValueError("No result[] array in TinyTuya cloud status")
        temp, selected_dp_key, raw_value = _find_temperature_from_cloud_status(rows, preferred_dp)
        if temp is None:
            raise ValueError("No plausible temperature value found in cloud status payload")
        source = "cloud"

    return {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "device_id": args.device_id,
        "device_ip": args.ip if source == "local" else "cloud",
        "device_mac": _normalize_mac(args.device_mac),
        "temperature_c": temp,
        "dps_key": selected_dp_key,
        "raw_value": raw_value,
        "source": source,
    }


def _should_emit(prev_payload: dict[str, Any] | None, new_payload: dict[str, Any], min_delta_c: float) -> bool:
    if prev_payload is None:
        return True
    prev_temp = _to_number(prev_payload.get("temperature_c"))
    new_temp = _to_number(new_payload.get("temperature_c"))
    if prev_temp is None or new_temp is None:
        return True
    return abs(new_temp - prev_temp) >= min_delta_c


def _collect_once(args: argparse.Namespace) -> int:
    try:
        payload = _build_payload(args)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    _write_json(args.output_json, payload)
    _append_csv(args.output_csv, payload)
    print(json.dumps(payload, ensure_ascii=True))
    return 0


def _collect_watch(args: argparse.Namespace) -> int:
    interval_seconds = max(1.0, float(args.poll_seconds))
    min_delta_c = max(0.0, float(args.min_delta_c))
    watch_seconds = max(0.0, float(args.watch_seconds))
    started = time.time()
    prev_payload: dict[str, Any] | None = None

    while True:
        if watch_seconds > 0 and (time.time() - started) >= watch_seconds:
            return 0

        try:
            payload = _build_payload(args)
            if _should_emit(prev_payload, payload, min_delta_c):
                _write_json(args.output_json, payload)
                _append_csv(args.output_csv, payload)
                print(json.dumps(payload, ensure_ascii=True))
                prev_payload = payload
            else:
                print("INFO: no significant temperature change")
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: {exc}")

        time.sleep(interval_seconds)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture TinyTuya temperature and export latest JSON + CSV history."
    )
    parser.add_argument("--scan", action="store_true", help="Scan Tuya devices on LAN and print JSON list.")
    parser.add_argument("--scan-time", type=float, default=8.0, help="Scan duration in seconds.")
    parser.add_argument("--watch", action="store_true", help="Continuous polling mode.")
    parser.add_argument(
        "--watch-seconds",
        type=float,
        default=float(os.getenv("TUYA_WATCH_SECONDS", "0")),
        help="Stop watch mode after N seconds (0 = infinite).",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=float(os.getenv("TUYA_POLL_SECONDS", "30")),
        help="Polling interval in seconds for watch mode.",
    )
    parser.add_argument(
        "--min-delta-c",
        type=float,
        default=float(os.getenv("TUYA_MIN_DELTA_C", "0.1")),
        help="Minimum temperature delta to append a new sample in watch mode.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=int(os.getenv("TUYA_CAPTURE_RETRIES", "3")),
        help="Number of retries for a single TinyTuya status read.",
    )
    parser.add_argument(
        "--retry-delay-seconds",
        type=float,
        default=float(os.getenv("TUYA_CAPTURE_RETRY_DELAY_SECONDS", "1.5")),
        help="Delay between status read retries.",
    )

    parser.add_argument(
        "--mode",
        default=os.getenv("TUYA_CAPTURE_MODE", "local"),
        help="Capture mode: local, cloud, or auto (fallback local->cloud).",
    )

    parser.add_argument("--device-id", default=os.getenv("TUYA_TINYTUYA_DEVICE_ID", ""), help="Tuya device id")
    parser.add_argument("--local-key", default=os.getenv("TUYA_TINYTUYA_LOCAL_KEY", ""), help="Tuya local key")
    parser.add_argument("--ip", default=os.getenv("TUYA_TINYTUYA_IP", ""), help="Tuya local device IP")
    parser.add_argument("--version", default=os.getenv("TUYA_TINYTUYA_VERSION", "3.3"), help="Protocol version, e.g. 3.3")
    parser.add_argument("--api-key", default=os.getenv("TUYA_CLOUD_API_KEY", ""), help="Tuya Cloud API key")
    parser.add_argument("--api-secret", default=os.getenv("TUYA_CLOUD_API_SECRET", ""), help="Tuya Cloud API secret")
    parser.add_argument("--api-region", default=os.getenv("TUYA_CLOUD_API_REGION", "eu"), help="Tuya Cloud API region")
    parser.add_argument("--device-mac", default="", help="Known device MAC (for output traceability)")
    parser.add_argument("--target-macs", default=os.getenv("TUYA_TARGET_MACS", ""), help="Comma-separated MAC list")
    parser.add_argument("--temperature-dp", default="", help="Optional explicit DPS key for temperature")

    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path(os.getenv("TUYA_LATEST_JSON_PATH", "data/tuya_temperature_latest.json")),
        help="Path to write latest temperature JSON",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path(os.getenv("TUYA_HISTORY_CSV_PATH", "data/tuya_temperature_history.csv")),
        help="Path to append temperature CSV history",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.scan:
        devices = _scan_devices(max_time=args.scan_time)
        targets = {_normalize_mac(mac) for mac in _split_csv_values(args.target_macs)}
        if targets:
            devices = [device for device in devices if _normalize_mac(str(device.get("mac", ""))) in targets]
        print(json.dumps(devices, ensure_ascii=True, indent=2))
        return 0

    mode = str(args.mode).lower()
    has_local = bool(args.local_key and args.ip)
    has_cloud = bool(args.api_key and args.api_secret)

    if not args.device_id:
        parser.error("--device-id is required when --scan is not used")
    if mode == "local" and not has_local:
        parser.error("--local-key and --ip are required in local mode")
    if mode == "cloud" and not has_cloud:
        parser.error("--api-key and --api-secret are required in cloud mode")
    if mode == "auto" and not (has_local or has_cloud):
        parser.error("auto mode requires local creds (--local-key/--ip) and/or cloud creds (--api-key/--api-secret)")

    if not args.device_mac:
        target_macs = _split_csv_values(args.target_macs)
        if len(target_macs) == 1:
            args.device_mac = target_macs[0]

    # Allow runtime disable through env while keeping script reusable.
    if _bool_env("TUYA_ENABLED", default=True) is False:
        print("INFO: TUYA_ENABLED=0, skipping capture")
        return 0

    if args.watch:
        return _collect_watch(args)
    return _collect_once(args)


if __name__ == "__main__":
    raise SystemExit(main())
