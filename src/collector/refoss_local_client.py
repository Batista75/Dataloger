from __future__ import annotations

import random
import socket
import threading
from datetime import datetime, timezone
from typing import Any

from src.core.config import settings
from src.db.repository import Measurement


class RefossLocalClient:
	REFOSS_PORT = 9989
	REFOSS_BROADCAST_ADDR = "255.255.255.255"
	DISCOVERY_TIMEOUT = 5

	def __init__(self) -> None:
		self._last_measurement: dict[str, Any] | None = None
		self._lock = threading.Lock()
		self._device_ip: str | None = settings.refoss_device_ip or None

	def discover_device(self) -> str | None:
		if self._device_ip:
			return self._device_ip
		sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
		sock.settimeout(self.DISCOVERY_TIMEOUT)
		try:
			sock.sendto(b"discovery", (self.REFOSS_BROADCAST_ADDR, self.REFOSS_PORT))
			while True:
				try:
					data, addr = sock.recvfrom(1024)
					if data and isinstance(addr, tuple) and addr[0]:
						return addr[0]
				except socket.timeout:
					break
		finally:
			sock.close()
		return None

	def read_measurement(self) -> Measurement:
		if self._device_ip is None:
			self._device_ip = self.discover_device()
			if self._device_ip is None:
				raise ConnectionError("Refoss EM06 device not discovered on LAN")
		if not settings.refoss_allow_simulated_fallback:
			raise NotImplementedError(
				"Refoss local parser not implemented yet. Set REFOSS_ALLOW_SIMULATED_FALLBACK=1 to enable simulated data."
			)
		return self._read_mock()

	def _read_mock(self) -> Measurement:
		voltage_v = round(230 + random.uniform(-2, 2), 2)
		frequency_hz = round(50 + random.uniform(-0.05, 0.05), 2)
		power_factor = round(random.uniform(0.88, 0.99), 3)
		a1_cons = round(random.uniform(0.5, 2.0), 4)
		b1_cons = round(random.uniform(0.5, 2.0), 4)
		c1_cons = round(random.uniform(0.5, 2.0), 4)
		a2_cons = round(random.uniform(-1.5, 1.5), 4)
		b2_cons = round(random.uniform(-1.5, 1.5), 4)
		c2_cons = round(random.uniform(-1.5, 1.5), 4)
		with self._lock:
			if self._last_measurement is None:
				self._last_measurement = {"total_consumption_kwh": 0.0}
			total_consumption = (a1_cons + b1_cons + c1_cons + abs(a2_cons) + abs(b2_cons) + abs(c2_cons)) * (3 / 3600.0)
			self._last_measurement["total_consumption_kwh"] += total_consumption
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
			total_consumption_kwh=round(self._last_measurement.get("total_consumption_kwh", 0.0), 6),
			voltage_v=voltage_v,
			frequency_hz=frequency_hz,
			power_factor=power_factor,
			quality_flag=0,
		)
