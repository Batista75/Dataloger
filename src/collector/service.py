from __future__ import annotations

from collections import deque
import threading
from datetime import datetime, timedelta, timezone

from src.collector.em06_client import EM06Client
from src.core.channel_polarity import apply_channel_polarity
from src.core.config import settings
from src.core.power_slots import try_commit_closed_slots
from src.core.quality_flags import QUALITY_LIVE
from src.db.repository import Measurement
from src.db.repository import MeasurementRepository


CHANNELS = ("a1", "b1", "c1", "a2", "b2", "c2")
POWER_INTERVAL_SECONDS = 20
WATT_HISTORY_SIZE = 20
MOVING_AVG_WINDOW_SAMPLES = 4
OUTLIER_RATIO = 0.5
POWER_MIN_W = -6000.0
POWER_MAX_W = 9000.0
SAMPLES_20S_PER_HOUR = 180
HOURS_PER_DAY = 24


class CollectorService:
	def __init__(self, repo: MeasurementRepository) -> None:
		self.repo = repo
		self.client = EM06Client()
		self._stop_event = threading.Event()
		self._thread: threading.Thread | None = None
		self.sensor_state = "starting"
		self.last_error: str | None = None
		self.last_sample_ts_utc: str | None = None
		self.publish_interval_seconds = POWER_INTERVAL_SECONDS
		self._prev_ts_utc: datetime | None = None
		self._last_commit_ts_utc: datetime | None = None
		self._confirmed_power_w: dict[str, float] = {channel: 0.0 for channel in CHANNELS}
		self._pending_outlier_w: dict[str, float | None] = {channel: None for channel in CHANNELS}
		self._raw_w_history: dict[str, deque[float]] = {
			channel: deque(maxlen=WATT_HISTORY_SIZE) for channel in CHANNELS
		}
		self._stable_w_history: dict[str, deque[float]] = {
			channel: deque(maxlen=WATT_HISTORY_SIZE) for channel in CHANNELS
		}
		self._consumption_index_kwh: dict[str, float] = {channel: 0.0 for channel in CHANNELS}
		self._production_index_kwh: dict[str, float] = {channel: 0.0 for channel in CHANNELS}
		self._kwh20_consumption_hist: dict[str, deque[float]] = {
			channel: deque(maxlen=SAMPLES_20S_PER_HOUR) for channel in CHANNELS
		}
		self._kwh20_production_hist: dict[str, deque[float]] = {
			channel: deque(maxlen=SAMPLES_20S_PER_HOUR) for channel in CHANNELS
		}
		self._kwh1h_consumption_hist: dict[str, deque[float]] = {
			channel: deque(maxlen=HOURS_PER_DAY) for channel in CHANNELS
		}
		self._kwh1h_production_hist: dict[str, deque[float]] = {
			channel: deque(maxlen=HOURS_PER_DAY) for channel in CHANNELS
		}
		self.kwh_1h_consumption: dict[str, float] = {channel: 0.0 for channel in CHANNELS}
		self.kwh_1h_production: dict[str, float] = {channel: 0.0 for channel in CHANNELS}
		self.kwh_24h_consumption: dict[str, float] = {channel: 0.0 for channel in CHANNELS}
		self.kwh_24h_production: dict[str, float] = {channel: 0.0 for channel in CHANNELS}
		self._riemann_ready = False

	def start(self) -> None:
		if self._thread and self._thread.is_alive():
			return
		self._initialize_riemann_state()
		self._stop_event.clear()
		self._thread = threading.Thread(target=self._run, name="collector-service", daemon=True)
		self._thread.start()

	def stop(self) -> None:
		self._stop_event.set()
		if self._thread:
			self._thread.join(timeout=5)

	def _run(self) -> None:
		interval = max(settings.poll_seconds, 1)
		while not self._stop_event.is_set():
			try:
				measurement = self.client.read_measurement(poll_seconds=interval)
				measurement = self._apply_left_riemann_correction(measurement)
				measurement.quality_flag = QUALITY_LIVE
				self.repo.insert_measurement(measurement)
				try_commit_closed_slots(self.repo, settings)
				self.sensor_state = "connected"
				self.last_error = None
				self.last_sample_ts_utc = measurement.ts_utc
			except Exception as exc:
				self.sensor_state = "error"
				self.last_error = str(exc)
				now = datetime.now(timezone.utc).isoformat()
				self.repo.log_event("ERROR", "collector", self.last_error, now)
			self._stop_event.wait(interval)

	def _initialize_riemann_state(self) -> None:
		latest = self.repo.get_latest()
		if latest is None:
			return

		for channel in CHANNELS:
			self._consumption_index_kwh[channel] = _to_float(latest.get(f"{channel}_consumption_kwh"))
			self._production_index_kwh[channel] = _to_float(latest.get(f"{channel}_production_kwh"))

		self._prev_ts_utc = _parse_ts_utc(latest.get("ts_utc"))
		self._last_commit_ts_utc = self._prev_ts_utc
		self._riemann_ready = False

	def get_channels_power_w(self) -> dict[str, float]:
		return {channel: round(float(self._confirmed_power_w.get(channel, 0.0)), 3) for channel in CHANNELS}

	def _apply_left_riemann_correction(self, measurement: Measurement) -> Measurement:
		current_ts_utc = _parse_ts_utc(measurement.ts_utc)
		raw_signed_power_w = apply_channel_polarity(_extract_signed_power_w(measurement))

		if settings.em06_mode == "refoss_local_socket":
			stable_signed_power_w = {}
			for channel in CHANNELS:
				raw_value = float(raw_signed_power_w.get(channel, 0.0))
				safe_value = min(max(raw_value, POWER_MIN_W), POWER_MAX_W)
				stable_signed_power_w[channel] = safe_value
				self._stable_w_history[channel].append(safe_value)
				self._confirmed_power_w[channel] = safe_value
		else:
			stable_signed_power_w = self._smooth_and_validate_power(raw_signed_power_w)

		if self._riemann_ready:
			self._apply_20s_integration(stable_signed_power_w, current_ts_utc)

		for channel in CHANNELS:
			setattr(measurement, f"{channel}_power_w", round(float(stable_signed_power_w[channel]), 3))

		for channel in CHANNELS:
			setattr(measurement, f"{channel}_consumption_kwh", round(self._consumption_index_kwh[channel], 6))
			setattr(measurement, f"{channel}_production_kwh", round(self._production_index_kwh[channel], 6))

		measurement.total_consumption_kwh = round(sum(self._consumption_index_kwh.values()), 6)
		measurement.total_production_kwh = round(sum(self._production_index_kwh.values()), 6)

		self._prev_ts_utc = current_ts_utc
		self._riemann_ready = True
		return measurement

	def _smooth_and_validate_power(self, raw_signed_power_w: dict[str, float]) -> dict[str, float]:
		stable_values: dict[str, float] = {}

		for channel in CHANNELS:
			moving_avg = _mean_tail(self._raw_w_history[channel], MOVING_AVG_WINDOW_SAMPLES)
			confirmed = self._confirmed_power_w[channel]
			raw_value = float(raw_signed_power_w.get(channel, 0.0))

			# Hard safety bounds: if value is out of physical range, keep previous confirmed value.
			if raw_value < POWER_MIN_W or raw_value > POWER_MAX_W:
				raw_value = confirmed

			self._raw_w_history[channel].append(raw_value)
			moving_avg = _mean_tail(self._raw_w_history[channel], MOVING_AVG_WINDOW_SAMPLES)
			pending = self._pending_outlier_w[channel]

			if pending is not None:
				if _relative_variation(pending, moving_avg) <= OUTLIER_RATIO:
					confirmed = pending
				self._pending_outlier_w[channel] = None

			if _relative_variation(confirmed, moving_avg) > OUTLIER_RATIO:
				self._pending_outlier_w[channel] = moving_avg
				stable_value = confirmed
			else:
				stable_value = moving_avg
				self._confirmed_power_w[channel] = stable_value

			self._stable_w_history[channel].append(stable_value)
			stable_values[channel] = stable_value

		return stable_values

	def _apply_20s_integration(self, stable_signed_power_w: dict[str, float], current_ts_utc: datetime) -> None:
		if self._last_commit_ts_utc is None:
			self._last_commit_ts_utc = current_ts_utc
			return

		elapsed_seconds = (current_ts_utc - self._last_commit_ts_utc).total_seconds()
		if elapsed_seconds <= 0:
			return

		for channel in CHANNELS:
			stable_w = _mean_tail(self._stable_w_history[channel], WATT_HISTORY_SIZE)
			energy_delta_kwh = abs(stable_w) * elapsed_seconds / 3600000.0

			if stable_w >= 0:
				self._consumption_index_kwh[channel] += energy_delta_kwh
			else:
				self._production_index_kwh[channel] += energy_delta_kwh

			self._confirmed_power_w[channel] = stable_signed_power_w[channel]

		self._last_commit_ts_utc = current_ts_utc


def _parse_ts_utc(ts_value: object) -> datetime:
	if isinstance(ts_value, str) and ts_value.strip():
		try:
			return datetime.fromisoformat(ts_value.replace("Z", "+00:00")).astimezone(timezone.utc)
		except ValueError:
			pass
	return datetime.now(timezone.utc)


def _to_float(value: object) -> float:
	if value is None:
		return 0.0
	try:
		return max(float(value), 0.0)
	except (TypeError, ValueError):
		return 0.0


def _extract_signed_power_w(measurement: Measurement) -> dict[str, float]:
	powers: dict[str, float] = {}
	for channel in CHANNELS:
		consumption = _to_float(getattr(measurement, f"{channel}_consumption_kwh"))
		production = _to_float(getattr(measurement, f"{channel}_production_kwh"))
		net_value = consumption - production
		# Most payloads expose kW-scale values; convert to W for integration.
		if abs(net_value) <= 40:
			net_value *= 1000.0
		powers[channel] = net_value
	return powers


def _mean_tail(values: deque[float], size: int) -> float:
	if not values:
		return 0.0
	window = list(values)[-max(1, size):]
	return sum(window) / len(window)


def _mean_all(values: deque[float]) -> float:
	if not values:
		return 0.0
	return sum(values) / len(values)


def _relative_variation(base: float, candidate: float) -> float:
	base_abs = max(abs(base), 1.0)
	return abs(candidate - base) / base_abs
