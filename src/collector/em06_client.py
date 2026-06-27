from __future__ import annotations

import hashlib
import json
import random
import re
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlencode, urlparse
from datetime import datetime, timezone
from threading import Event, Lock
from typing import Any

import paho.mqtt.client as mqtt
import requests
from requests.auth import HTTPDigestAuth

from src.core.config import settings
from src.db.repository import Measurement
from src.collector.refoss_local_client import RefossLocalClient


CHANNEL_BY_ID = {
	1: "a1",
	2: "b1",
	3: "c1",
	4: "a2",
	5: "b2",
	6: "c2",
}


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
		try:
			return self._read_refoss_http_rpc()
		except PermissionError as exc:
			if not settings.refoss_allow_simulated_fallback:
				raise PermissionError(
					"Refoss digest authentication failed. Configure EM06_HTTP_USERNAME/EM06_HTTP_PASSWORD or enable REFOSS_ALLOW_SIMULATED_FALLBACK=1."
				) from exc
			if self._refoss_client is None:
				self._refoss_client = RefossLocalClient()
			return self._refoss_client.read_measurement()
		except requests.RequestException as exc:
			raise ConnectionError(f"Refoss local RPC failed: {exc}") from exc

	def _read_refoss_http_rpc(self) -> Measurement:
		# Refoss RPC variants may expose aggregate masks, full status maps, or per-channel queries.
		for params in ({"id": 65535}, {"id": 63}, {"id": 127}):
			payload = _fetch_refoss_rpc_json("Em.Status.Get", params)
			entries = _extract_refoss_em_entries(payload)
			if entries:
				return _measurement_from_refoss_status({"result": {"status": entries}})

		entries: list[dict[str, Any]] = []
		for channel_id in range(1, 7):
			payload = _fetch_refoss_rpc_json("Em.Status.Get", {"id": channel_id})
			channel_entries = _extract_refoss_em_entries(payload)
			if channel_entries:
				entries.append(channel_entries[0])

		if not entries:
			raise ValueError("Refoss EM06P RPC returned no em channel values")

		return _measurement_from_refoss_status({"result": {"status": entries}})

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
				client_id=settings.em06_mqtt_client_id or None,
				username=settings.em06_mqtt_username or None,
				password=settings.em06_mqtt_password or None,
			)

		payload = self._mqtt_client.wait_for_payload(timeout_seconds=max(timeout_seconds, 1))
		payload_dict = _extract_measurement_dict(payload)
		return _measurement_from_payload(payload_dict)

	def _read_meross_local_post(self) -> Measurement:
		if not settings.em06_http_url:
			raise ValueError("EM06_HTTP_URL is required when EM06_MODE=meross_local_post")
		if not settings.em06_meross_key:
			raise ValueError(
				"EM06_MEROSS_KEY is required for meross_local_post mode. "
				"Find it in the Refoss app: device → settings → About → Key."
			)
		return _meross_post_all_channels(
			base_url=settings.em06_http_url,
			key=settings.em06_meross_key,
			timeout=settings.em06_timeout_seconds,
		)

	def _read_mock(self, poll_seconds: int) -> Measurement:
		voltage_v = round(230 + random.uniform(-2, 2), 2)
		frequency_hz = round(50 + random.uniform(-0.05, 0.05), 2)
		power_factor = round(random.uniform(0.88, 0.99), 3)
		a1_cons = round(random.uniform(0.5, 2.0), 4)
		b1_cons = round(random.uniform(0.5, 2.0), 4)
		c1_cons = round(random.uniform(0.5, 2.0), 4)
		a2_cons = round(random.uniform(-1.5, 1.5), 4)
		b2_cons = round(random.uniform(-1.5, 1.5), 4)
		c2_cons = round(random.uniform(-1.5, 1.5), 4)
		self._energy_kwh += (a1_cons + b1_cons + c1_cons + abs(a2_cons) + abs(b2_cons) + abs(c2_cons)) * (poll_seconds / 3600.0)
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
	total_production = sum(v for k, v in channels.items() if k.endswith("_production_kwh") and v is not None)
	total_consumption = sum(v for k, v in channels.items() if k.endswith("_consumption_kwh") and v is not None)
	voltage_v = _pick_float(payload_dict, ["voltage_v", "voltage", "volt"])
	frequency_hz = _pick_float(payload_dict, ["frequency_hz", "frequency", "hz"])
	power_factor = _pick_float(payload_dict, ["power_factor", "pf", "cosphi"])
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


def _measurement_from_refoss_status(payload: dict[str, Any]) -> Measurement:
	root = payload.get("result", payload)
	if not isinstance(root, dict):
		raise ValueError("Refoss Em.Status.Get payload is invalid")

	statuses = root.get("status")
	if not isinstance(statuses, list) or not statuses:
		raise ValueError("Refoss Em.Status.Get returned no status list")

	fields: dict[str, float | None] = {
		"a1_production_kwh": None,
		"a1_consumption_kwh": None,
		"b1_production_kwh": None,
		"b1_consumption_kwh": None,
		"c1_production_kwh": None,
		"c1_consumption_kwh": None,
		"a2_production_kwh": None,
		"a2_consumption_kwh": None,
		"b2_production_kwh": None,
		"b2_consumption_kwh": None,
		"c2_production_kwh": None,
		"c2_consumption_kwh": None,
	}

	voltage_values: list[float] = []
	pf_values: list[float] = []

	for status in statuses:
		if not isinstance(status, dict):
			continue
		channel_id = int(_to_float(status.get("id")) or 0)
		channel_name = CHANNEL_BY_ID.get(channel_id)
		if not channel_name:
			continue

		power_w = _to_float(status.get("power")) or 0.0
		signed_kw = power_w / 1000.0
		fields[f"{channel_name}_consumption_kwh"] = round(max(signed_kw, 0.0), 6)
		fields[f"{channel_name}_production_kwh"] = round(max(-signed_kw, 0.0), 6)

		voltage = _to_float(status.get("voltage"))
		if voltage is not None:
			voltage_values.append(voltage)
		pf = _to_float(status.get("pf"))
		if pf is not None:
			pf_values.append(pf)

	total_consumption = sum(v for k, v in fields.items() if k.endswith("_consumption_kwh") and v is not None)
	total_production = sum(v for k, v in fields.items() if k.endswith("_production_kwh") and v is not None)
	voltage_v = round(sum(voltage_values) / len(voltage_values), 2) if voltage_values else None
	power_factor = round(sum(pf_values) / len(pf_values), 3) if pf_values else None

	return Measurement(
		ts_utc=_extract_timestamp(root),
		a1_production_kwh=fields["a1_production_kwh"],
		a1_consumption_kwh=fields["a1_consumption_kwh"],
		b1_production_kwh=fields["b1_production_kwh"],
		b1_consumption_kwh=fields["b1_consumption_kwh"],
		c1_production_kwh=fields["c1_production_kwh"],
		c1_consumption_kwh=fields["c1_consumption_kwh"],
		a2_production_kwh=fields["a2_production_kwh"],
		a2_consumption_kwh=fields["a2_consumption_kwh"],
		b2_production_kwh=fields["b2_production_kwh"],
		b2_consumption_kwh=fields["b2_consumption_kwh"],
		c2_production_kwh=fields["c2_production_kwh"],
		c2_consumption_kwh=fields["c2_consumption_kwh"],
		total_production_kwh=round(total_production, 6),
		total_consumption_kwh=round(total_consumption, 6),
		voltage_v=voltage_v,
		frequency_hz=None,
		power_factor=power_factor,
		quality_flag=1,
	)


def _fetch_refoss_rpc_json(method: str, params: dict[str, Any]) -> dict[str, Any]:
	url = _build_refoss_rpc_url(method, params)
	auth: HTTPDigestAuth | None = None
	if settings.em06_http_username and settings.em06_http_password:
		auth = HTTPDigestAuth(settings.em06_http_username, settings.em06_http_password)

	response = requests.get(url, timeout=settings.em06_timeout_seconds, auth=auth)
	if response.status_code in {401, 403}:
		raise PermissionError("Refoss digest authentication failed")
	response.raise_for_status()

	try:
		payload = response.json()
	except ValueError as exc:
		raise ValueError(f"Refoss {method} response is not valid JSON") from exc

	if not isinstance(payload, dict):
		raise ValueError(f"Refoss {method} payload is not an object")
	return payload


def _extract_refoss_em_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
	root = payload.get("result", payload)
	if not isinstance(root, dict):
		return []

	status = root.get("status", root)
	if isinstance(status, list):
		return [item for item in status if isinstance(item, dict) and _to_float(item.get("id")) is not None]

	entries: list[dict[str, Any]] = []
	if isinstance(status, dict):
		for key, value in status.items():
			if not isinstance(value, dict):
				continue
			match = re.match(r"^em:(\d+)$", str(key))
			if match:
				entry = dict(value)
				entry.setdefault("id", int(match.group(1)))
				entries.append(entry)

		em_value = status.get("em")
		if isinstance(em_value, list):
			for item in em_value:
				if isinstance(item, dict):
					entry = dict(item)
					if _to_float(entry.get("id")) is not None:
						entries.append(entry)
		elif isinstance(em_value, dict):
			for key, value in em_value.items():
				if not isinstance(value, dict):
					continue
				entry = dict(value)
				if _to_float(entry.get("id")) is None:
					cid = _to_float(key)
					if cid is not None:
						entry["id"] = int(cid)
				if _to_float(entry.get("id")) is not None:
					entries.append(entry)

	entries_by_id: dict[int, dict[str, Any]] = {}
	for item in entries:
		channel_id = int(_to_float(item.get("id")) or 0)
		if channel_id > 0:
			entries_by_id[channel_id] = item

	return [entries_by_id[key] for key in sorted(entries_by_id)]


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
	keys = {key.lower() for key in payload.keys()}
	multi_channel_keys = {
		"a1_production_kwh", "a1_consumption_kwh",
		"b1_production_kwh", "b1_consumption_kwh",
		"c1_production_kwh", "c1_consumption_kwh",
		"a2_production_kwh", "a2_consumption_kwh",
		"b2_production_kwh", "b2_consumption_kwh",
		"c2_production_kwh", "c2_consumption_kwh",
	}
	legacy_keys = {
		"power_w", "power", "energy_kwh", "energy",
		"voltage_v", "voltage", "current_a", "current",
		"frequency_hz", "frequency", "power_factor", "pf",
	}
	has_multi = len(keys & multi_channel_keys) >= 2
	has_legacy = len(keys & legacy_keys) >= 2
	return has_multi or has_legacy


def _extract_timestamp(payload: dict[str, Any]) -> str:
	for key in ("ts_utc", "timestamp", "datetime", "time"):
		value = payload.get(key)
		if isinstance(value, str) and value:
			return value
	for key in ("unixtime", "ts"):
		value = payload.get(key)
		if isinstance(value, (int, float)):
			return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
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


def _meross_sign(msg_id: str, key: str, timestamp: int) -> str:
	return hashlib.md5(f"{msg_id}{key}{timestamp}".encode()).hexdigest()


def _meross_post(url: str, namespace: str, payload: dict[str, Any], key: str, timeout: int) -> dict[str, Any]:
	import time as _time
	msg_id = uuid.uuid4().hex
	ts = int(_time.time())
	sign = _meross_sign(msg_id, key, ts)
	body = json.dumps({
		"header": {
			"from": "", "messageId": msg_id, "method": "GET",
			"namespace": namespace, "payloadVersion": 1,
			"sign": sign, "timestamp": ts, "triggerSrc": "Android",
		},
		"payload": payload,
	}).encode("utf-8")
	req = urllib.request.Request(
		url, data=body, method="POST",
		headers={"Content-Type": "application/json"},
	)
	try:
		with urllib.request.urlopen(req, timeout=timeout) as r:
			raw = r.read()
	except urllib.error.HTTPError as exc:
		raise ConnectionError(f"Meross HTTP error: {exc.code} {exc.reason}") from exc
	except urllib.error.URLError as exc:
		raise ConnectionError(f"Meross network error: {exc}") from exc
	if not raw:
		raise ConnectionError("Meross device closed connection without response (check EM06_MEROSS_KEY)")
	try:
		return json.loads(raw.decode("utf-8"))
	except json.JSONDecodeError as exc:
		raise ValueError("Meross response is not valid JSON") from exc


def _meross_post_all_channels(base_url: str, key: str, timeout: int) -> Measurement:
	url = base_url.rstrip("/") + "/config"
	channel_data: dict[int, dict[str, Any]] = {}
	for ch in range(6):
		resp = _meross_post(url, "Appliance.Control.Electricity", {"channel": ch}, key, timeout)
		elec = resp.get("payload", {}).get("electricity")
		if isinstance(elec, dict):
			channel_data[ch] = elec
		elif isinstance(elec, list) and elec:
			for item in elec:
				if isinstance(item, dict) and "channel" in item:
					channel_data[int(item["channel"])] = item
			if ch in channel_data:
				pass
			elif elec:
				channel_data[ch] = elec[0]

	# Map channels 0..5 → a1, b1, c1, a2, b2, c2
	chan_names = ["a1", "b1", "c1", "a2", "b2", "c2"]
	fields: dict[str, float | None] = {}
	voltage_values: list[float] = []
	pf_values: list[float] = []

	for idx, name in enumerate(chan_names):
		ch = channel_data.get(idx, {})
		power_mw = _to_float(ch.get("power")) or 0.0
		power_w = power_mw / 1000.0
		fields[f"{name}_consumption_kwh"] = round(max(power_w, 0.0), 6)
		fields[f"{name}_production_kwh"] = round(max(-power_w, 0.0), 6)
		v = _to_float(ch.get("voltage"))
		if v is not None:
			voltage_values.append(v / 10.0)
		c = _to_float(ch.get("current"))
		p = abs(power_w)
		v_val = (v / 10.0) if v is not None else None
		if v_val and v_val > 0 and p > 0:
			pf_values.append(p / (v_val * (c / 1000.0)) if c else 1.0)

	total_cons = sum(fields.get(f"{n}_consumption_kwh") or 0.0 for n in chan_names)
	total_prod = sum(fields.get(f"{n}_production_kwh") or 0.0 for n in chan_names)
	voltage_v = round(sum(voltage_values) / len(voltage_values), 2) if voltage_values else None

	return Measurement(
		ts_utc=_extract_timestamp({}),
		a1_consumption_kwh=fields.get("a1_consumption_kwh"),
		a1_production_kwh=fields.get("a1_production_kwh"),
		b1_consumption_kwh=fields.get("b1_consumption_kwh"),
		b1_production_kwh=fields.get("b1_production_kwh"),
		c1_consumption_kwh=fields.get("c1_consumption_kwh"),
		c1_production_kwh=fields.get("c1_production_kwh"),
		a2_consumption_kwh=fields.get("a2_consumption_kwh"),
		a2_production_kwh=fields.get("a2_production_kwh"),
		b2_consumption_kwh=fields.get("b2_consumption_kwh"),
		b2_production_kwh=fields.get("b2_production_kwh"),
		c2_consumption_kwh=fields.get("c2_consumption_kwh"),
		c2_production_kwh=fields.get("c2_production_kwh"),
		total_consumption_kwh=round(total_cons, 6),
		total_production_kwh=round(total_prod, 6),
		voltage_v=voltage_v,
		frequency_hz=None,
		power_factor=None,
		quality_flag=1,
	)


def _build_refoss_rpc_url(method: str, params: dict[str, Any]) -> str:
	base = settings.em06_http_url.strip() or settings.refoss_device_ip.strip()
	if not base:
		raise ValueError("Set EM06_HTTP_URL or REFOSS_DEVICE_IP for refoss_local_socket mode")
	if "://" not in base:
		base = f"http://{base}"
	parsed = urlparse(base)
	netloc = parsed.netloc or parsed.path
	if not netloc:
		raise ValueError(f"Invalid Refoss base URL: {base}")
	query = urlencode(params)
	return f"{parsed.scheme or 'http'}://{netloc}/rpc/{method}?{query}"


class MqttSnapshotClient:
	def __init__(
		self,
		host: str,
		port: int,
		topic: str,
		client_id: str | None,
		username: str | None,
		password: str | None,
	) -> None:
		self.host = host
		self.port = port
		self.topic = topic
		self._payload_event = Event()
		self._latest_payload: dict[str, Any] | None = None
		self._lock = Lock()

		self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id or "")
		if username:
			self._client.username_pw_set(username=username, password=password)
		self._client.on_connect = self._on_connect
		self._client.on_message = self._on_message
		self._client.connect(self.host, self.port, keepalive=30)
		self._client.loop_start()

	def wait_for_payload(self, timeout_seconds: int) -> dict[str, Any]:
		self._payload_event.clear()
		if not self._payload_event.wait(timeout=timeout_seconds):
			raise TimeoutError(f"No MQTT payload received on topic {self.topic} within {timeout_seconds}s")
		with self._lock:
			if self._latest_payload is None:
				raise TimeoutError(f"MQTT payload missing on topic {self.topic}")
			return self._latest_payload

	def _on_connect(self, client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any = None) -> None:
		client.subscribe(self.topic)

	def _on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
		try:
			payload = json.loads(msg.payload.decode("utf-8"))
		except json.JSONDecodeError as exc:
			raise ValueError("MQTT payload is not valid JSON") from exc
		with self._lock:
			self._latest_payload = payload
		self._payload_event.set()
