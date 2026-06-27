from __future__ import annotations

import json
import random
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from threading import Event, Lock
from typing import Any

import paho.mqtt.client as mqtt

from src.core.config import settings
from src.db.repository import Measurement
from src.collector.refoss_local_client import RefossLocalClient


class EM06Client:
    def __init__(self) -> None:
        self._energy_kwh = 0.0
        self._mqtt_client: MqttSnapshotClient | None = None
        self._refoss_client: RefossLocalClient | None = None

    def read_measurement(self, poll_seconds: int) -> Measurement:
        if settings.em06_mode == "refoss_local_socket":
            return self._read_refoss_local_socket()
        if settings.em06_mode == "mqtt_json":
            return self._read_mqtt_json(timeout_seconds=poll_seconds)
        if settings.em06_mode == "meross_local_post":
            return self._read_meross_local_post()
        if settings.em06_mode == "http_json":
            return self._read_http_json()
        return self._read_mock(poll_seconds=poll_seconds)

    def _read_refoss_local_socket(self) -> Measurement:
        if self._refoss_client is None:
            self._refoss_client = RefossLocalClient()
        return self._refoss_client.read_measurement()

    def _read_mqtt_json(self, timeout_seconds: int) -> Measurement:
        if not settings.em06_mqtt_host:
            raise ValueError("EM06_MQTT_HOST is required when EM06_MODE=mqtt_json")
        if not settings.em06_mqtt_topic:
            raise ValueError("EM06_MQTT_TOPIC is required when EM06_MODE=mqtt_json")

        if self._mqtt_client is None:
            self._mqtt_client = MqttSnapshotClient(
                host=settings.em06_mqtt_host,
                port=settings.em06_mqtt_port,
                topic=settings.em06_mqtt_topic,
                username=settings.em06_mqtt_username or None,
                password=settings.em06_mqtt_password or None,
            )

        payload = self._mqtt_client.wait_for_payload(timeout_seconds=max(timeout_seconds, 1))
        payload_dict = _extract_measurement_dict(payload)
        return _measurement_from_payload(payload_dict)

    def _read_meross_local_post(self) -> Measurement:
        if not settings.em06_http_url:
            raise ValueError("EM06_HTTP_URL is required when EM06_MODE=meross_local_post")

        request_payload = {
            "header": {
                "messageId": uuid.uuid4().hex,
                "namespace": settings.em06_namespace,
                "triggerSrc": "Local",
                "sign": "",
                "payloadVersion": 1,
            },
            "payload": {},
        }

        req = urllib.request.Request(
            settings.em06_http_url,
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps(request_payload).encode("utf-8"),
        )

        try:
            with urllib.request.urlopen(req, timeout=settings.em06_timeout_seconds) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise ConnectionError(f"EM06 HTTP error: {exc.code} {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise ConnectionError(f"EM06 network error: {exc}") from exc

        if not raw:
            raise ConnectionError(
                "EM06 returned an empty response. This usually means local API auth/signature is required."
            )

        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("EM06 response is not valid JSON") from exc

        payload_dict = _extract_measurement_dict(payload)
        return _measurement_from_payload(payload_dict)

    def _read_mock(self, poll_seconds: int) -> Measurement:
        """Generate mock multi-channel data (triphasé 3-phase with 2 meters)."""
        voltage_v = round(230 + random.uniform(-2, 2), 2)
        frequency_hz = round(50 + random.uniform(-0.05, 0.05), 2)
        power_factor = round(random.uniform(0.88, 0.99), 3)
        
        # Generate realistic consumption for each channel
        # Meter 1 (A1, B1, C1): Primary meter - more stable load
        a1_cons = round(random.uniform(0.5, 2.0), 4)
        b1_cons = round(random.uniform(0.5, 2.0), 4)
        c1_cons = round(random.uniform(0.5, 2.0), 4)
        
        # Meter 2 (A2, B2, C2): Secondary meter - may have solar production (negative)
        a2_cons = round(random.uniform(-1.5, 1.5), 4)  # Can be negative for solar injection
        b2_cons = round(random.uniform(-1.5, 1.5), 4)
        c2_cons = round(random.uniform(-1.5, 1.5), 4)
        
        # Accumulate energy
        self._energy_kwh += (a1_cons + b1_cons + c1_cons + abs(a2_cons) + abs(b2_cons) + abs(c2_cons)) * (poll_seconds / 3600.0)
        
        # Separate production (negative) and consumption (positive)
        a1_prod = 0.0 if a1_cons >= 0 else abs(a1_cons)
        b1_prod = 0.0 if b1_cons >= 0 else abs(b1_cons)
        c1_prod = 0.0 if c1_cons >= 0 else abs(c1_cons)
        a2_prod = max(a2_cons, 0.0) if a2_cons > 0 else abs(min(a2_cons, 0.0))
        b2_prod = max(b2_cons, 0.0) if b2_cons > 0 else abs(min(b2_cons, 0.0))
        c2_prod = max(c2_cons, 0.0) if c2_cons > 0 else abs(min(c2_cons, 0.0))

        return Measurement(
            ts_utc=datetime.now(timezone.utc).isoformat(),
            a1_production_kwh=round(a1_prod, 6),
            a1_consumption_kwh=round(max(a1_cons, 0.0), 6),
            b1_production_kwh=round(b1_prod, 6),
            b1_consumption_kwh=round(max(b1_cons, 0.0), 6),
            c1_production_kwh=round(c1_prod, 6),
            c1_consumption_kwh=round(max(c1_cons, 0.0), 6),
            a2_production_kwh=round(a2_prod, 6),
            a2_consumption_kwh=round(max(a2_cons, 0.0), 6),
            b2_production_kwh=round(b2_prod, 6),
            b2_consumption_kwh=round(max(b2_cons, 0.0), 6),
            c2_production_kwh=round(c2_prod, 6),
            c2_consumption_kwh=round(max(c2_cons, 0.0), 6),
            total_production_kwh=round(a1_prod + b1_prod + c1_prod + a2_prod + b2_prod + c2_prod, 6),
            total_consumption_kwh=round(max(a1_cons, 0.0) + max(b1_cons, 0.0) + max(c1_cons, 0.0) + max(a2_cons, 0.0) + max(b2_cons, 0.0) + max(c2_cons, 0.0), 6),
            voltage_v=voltage_v,
            frequency_hz=frequency_hz,
            power_factor=power_factor,
            quality_flag=1,
        )

    def _read_http_json(self) -> Measurement:
        if not settings.em06_http_url:
            raise ValueError("EM06_HTTP_URL is required when EM06_MODE=http_json")

        req = urllib.request.Request(settings.em06_http_url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=settings.em06_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ConnectionError(f"EM06 HTTP read failed: {exc}") from exc

        payload_dict = _extract_measurement_dict(payload)

        return _measurement_from_payload(payload_dict)


def _measurement_from_payload(payload_dict: dict[str, Any]) -> Measurement:
    """Extract multi-channel measurement from payload (6 channels + aggregates)."""
    
    # Extract 6 channels (A1, B1, C1, A2, B2, C2) with Production/Consumption each
    channels = {
        "a1_production_kwh": _pick_float(payload_dict, ["a1_production_kwh", "channel_a1_production", "a1_prod"]),
        "a1_consumption_kwh": _pick_float(payload_dict, ["a1_consumption_kwh", "channel_a1_consumption", "a1_cons"]),
        "b1_production_kwh": _pick_float(payload_dict, ["b1_production_kwh", "channel_b1_production", "b1_prod"]),
        "b1_consumption_kwh": _pick_float(payload_dict, ["b1_consumption_kwh", "channel_b1_consumption", "b1_cons"]),
        "c1_production_kwh": _pick_float(payload_dict, ["c1_production_kwh", "channel_c1_production", "c1_prod"]),
        "c1_consumption_kwh": _pick_float(payload_dict, ["c1_consumption_kwh", "channel_c1_consumption", "c1_cons"]),
        "a2_production_kwh": _pick_float(payload_dict, ["a2_production_kwh", "channel_a2_production", "a2_prod"]),
        "a2_consumption_kwh": _pick_float(payload_dict, ["a2_consumption_kwh", "channel_a2_consumption", "a2_cons"]),
        "b2_production_kwh": _pick_float(payload_dict, ["b2_production_kwh", "channel_b2_production", "b2_prod"]),
        "b2_consumption_kwh": _pick_float(payload_dict, ["b2_consumption_kwh", "channel_b2_consumption", "b2_cons"]),
        "c2_production_kwh": _pick_float(payload_dict, ["c2_production_kwh", "channel_c2_production", "c2_prod"]),
        "c2_consumption_kwh": _pick_float(payload_dict, ["c2_consumption_kwh", "channel_c2_consumption", "c2_cons"]),
    }
    
    # Calculate totals
    total_production = sum(v for k, v in channels.items() if k.endswith("_production_kwh") and v is not None)
    total_consumption = sum(v for k, v in channels.items() if k.endswith("_consumption_kwh") and v is not None)
    
    # Extract global properties
    voltage_v = _pick_float(payload_dict, ["voltage_v", "voltage", "volt"])
    frequency_hz = _pick_float(payload_dict, ["frequency_hz", "frequency", "hz"])
    power_factor = _pick_float(payload_dict, ["power_factor", "pf", "cosphi"])
    
    # Unit conversion for voltage/frequency if needed
    if voltage_v is not None and voltage_v > 1000:
        voltage_v = round(voltage_v / 10.0, 2)

    return Measurement(
        ts_utc=_extract_timestamp(payload_dict),
        a1_production_kwh=channels.get("a1_production_kwh"),
        a1_consumption_kwh=channels.get("a1_consumption_kwh"),
        b1_production_kwh=channels.get("b1_production_kwh"),
        b1_consumption_kwh=channels.get("b1_consumption_kwh"),
        c1_production_kwh=channels.get("c1_production_kwh"),
        c1_consumption_kwh=channels.get("c1_consumption_kwh"),
        a2_production_kwh=channels.get("a2_production_kwh"),
        a2_consumption_kwh=channels.get("a2_consumption_kwh"),
        b2_production_kwh=channels.get("b2_production_kwh"),
        b2_consumption_kwh=channels.get("b2_consumption_kwh"),
        c2_production_kwh=channels.get("c2_production_kwh"),
        c2_consumption_kwh=channels.get("c2_consumption_kwh"),
        total_production_kwh=total_production if total_production > 0 else None,
        total_consumption_kwh=total_consumption if total_consumption > 0 else None,
        voltage_v=voltage_v,
        frequency_hz=frequency_hz,
        power_factor=power_factor,
        quality_flag=1,
    )


def _extract_measurement_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        if _looks_like_measurement(payload):
            return payload
        for key in ("data", "result", "payload", "status"):
            candidate = payload.get(key)
            if isinstance(candidate, dict) and _looks_like_measurement(candidate):
                return candidate
            if isinstance(candidate, dict):
                for nested_key in ("electricity", "meter", "measurement", "measurements"):
                    nested = candidate.get(nested_key)
                    if isinstance(nested, dict) and _looks_like_measurement(nested):
                        return nested
            if isinstance(candidate, list) and candidate:
                last_item = candidate[-1]
                if isinstance(last_item, dict) and _looks_like_measurement(last_item):
                    return last_item
        return payload

    if isinstance(payload, list) and payload:
        last_item = payload[-1]
        if isinstance(last_item, dict):
            return last_item

    raise ValueError("EM06 response does not contain a readable measurement payload")


def _looks_like_measurement(payload: dict[str, Any]) -> bool:
    """Check if payload contains measurement data (single-phase OR multi-phase channels)."""
    keys = {key.lower() for key in payload.keys()}
    
    # Multi-channel detection (triphasé - 6 channels)
    multi_channel_keys = {
        "a1_production_kwh", "a1_consumption_kwh",
        "b1_production_kwh", "b1_consumption_kwh",
        "c1_production_kwh", "c1_consumption_kwh",
        "a2_production_kwh", "a2_consumption_kwh",
        "b2_production_kwh", "b2_consumption_kwh",
        "c2_production_kwh", "c2_consumption_kwh",
    }
    
    # Single-phase legacy detection
    legacy_keys = {
        "power_w", "power", "energy_kwh", "energy",
        "voltage_v", "voltage", "current_a", "current",
        "frequency_hz", "frequency", "power_factor", "pf",
    }
    
    # Check for at least 2 matching keys
    has_multi = len(keys & multi_channel_keys) >= 2
    has_legacy = len(keys & legacy_keys) >= 2
    
    return has_multi or has_legacy


def _extract_timestamp(payload: dict[str, Any]) -> str:
    for key in ("ts_utc", "timestamp", "datetime", "time"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return datetime.now(timezone.utc).isoformat()


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pick_float(payload: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        if key in payload:
            return _to_float(payload.get(key))
    return None


class MqttSnapshotClient:
    def __init__(
        self,
        host: str,
        port: int,
        topic: str,
        username: str | None,
        password: str | None,
    ) -> None:
        self.host = host
        self.port = port
        self.topic = topic
        self._payload_event = Event()
        self._latest_payload: dict[str, Any] | None = None
        self._lock = Lock()

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if username:
            self._client.username_pw_set(username=username, password=password)

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect(self.host, self.port, keepalive=30)
        self._client.loop_start()

    def _on_connect(self, client: mqtt.Client, _userdata: Any, _flags: Any, rc: int, _props: Any = None) -> None:
        if rc != 0:
            return
        client.subscribe(self.topic)

    def _on_message(self, _client: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if isinstance(payload, dict):
            with self._lock:
                self._latest_payload = payload
            self._payload_event.set()

    def wait_for_payload(self, timeout_seconds: int) -> dict[str, Any]:
        if self._payload_event.wait(timeout=timeout_seconds):
            with self._lock:
                if self._latest_payload is not None:
                    return self._latest_payload
        raise TimeoutError(
            f"No MQTT payload received on topic '{self.topic}' within {timeout_seconds}s"
        )
