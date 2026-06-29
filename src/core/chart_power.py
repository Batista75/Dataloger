from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

CHANNELS = ("a1", "b1", "c1", "a2", "b2", "c2")
GRAPH_CHANNELS = ("c1", "a2", "b2", "c2")
CHANNEL_TYPES: dict[str, str] = {
	"a1": "unused",
	"b1": "unused",
	"c1": "edf_total",
	"a2": "generator",
	"b2": "consumption",
	"c2": "consumption",
}

try:
	PARIS = ZoneInfo("Europe/Paris")
except Exception:
	PARIS = timezone(timedelta(hours=2))

DEFAULT_SLOT_MINUTES = 15
from src.core.quality_flags import QUALITY_LIVE, is_trusted_for_chart
MAX_SAMPLE_GAP_FACTOR = 4
DEFAULT_MIN_SAMPLES_PER_SLOT = 5


def _normalize_channel_power(value: float, channel: str) -> float:
	channel_type = CHANNEL_TYPES.get(channel, "consumption")
	if channel_type == "consumption":
		return max(0.0, value)
	return value


def _parse_ts_utc(value: object) -> datetime | None:
	if not isinstance(value, str) or not value.strip():
		return None
	try:
		return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
	except ValueError:
		return None


def _to_float(value: object) -> float | None:
	if value is None:
		return None
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def _parse_local_hhmm(value: str) -> tuple[int, int]:
	raw = str(value or "14:00").strip()
	parts = raw.split(":", 1)
	hour = int(parts[0])
	minute = int(parts[1]) if len(parts) > 1 else 0
	return hour, minute


def _parse_iso_date(value: str | None) -> date | None:
	if not value or not str(value).strip():
		return None
	return date.fromisoformat(str(value).strip())


def resolve_trusted_chart_from(
	day_start_utc: datetime,
	*,
	unreliable_from: date | None = None,
	unreliable_until: date | None = None,
	local_start_hhmm: str = "14:00",
) -> datetime:
	"""Earliest UTC instant used for chart power on this local day."""
	day_local = day_start_utc.astimezone(PARIS).date()
	if unreliable_from and unreliable_until and unreliable_from <= day_local <= unreliable_until:
		hour, minute = _parse_local_hhmm(local_start_hhmm)
		local_start = datetime(
			day_local.year,
			day_local.month,
			day_local.day,
			hour,
			minute,
			tzinfo=PARIS,
		)
		return local_start.astimezone(timezone.utc)
	return day_start_utc.astimezone(timezone.utc)


def _stored_power_w(row: dict[str, Any]) -> dict[str, float]:
	"""Chart uses stored instantaneous power only (no kWh index derivation)."""
	powers: dict[str, float] = {}
	for channel in CHANNELS:
		stored = _to_float(row.get(f"{channel}_power_w"))
		if stored is not None:
			powers[channel] = _normalize_channel_power(stored, channel)
	return powers


def _sample_is_trusted(
	row: dict[str, Any],
	prev_ts: datetime | None,
	trusted_from_utc: datetime,
	poll_seconds: int,
) -> bool:
	cur_ts = _parse_ts_utc(row.get("ts_utc"))
	if cur_ts is None or cur_ts < trusted_from_utc:
		return False

	if not is_trusted_for_chart(row.get("quality_flag")):
		return False

	max_gap = max(poll_seconds * MAX_SAMPLE_GAP_FACTOR, 15)
	if prev_ts is not None and (cur_ts - prev_ts).total_seconds() > max_gap:
		return False

	powers = _stored_power_w(row)
	if not any(channel in powers for channel in GRAPH_CHANNELS):
		return False
	return True


def build_chart_power_slots(
	rows: list[dict[str, Any]],
	day_start_utc: datetime,
	slot_minutes: int = DEFAULT_SLOT_MINUTES,
	trusted_from_utc: datetime | None = None,
	poll_seconds: int = 3,
	min_samples_per_slot: int = DEFAULT_MIN_SAMPLES_PER_SLOT,
) -> list[dict[str, Any]]:
	slot_minutes = max(5, min(60, int(slot_minutes)))
	slot_seconds = slot_minutes * 60
	slots_per_day = (24 * 60) // slot_minutes
	day_start = day_start_utc.astimezone(timezone.utc)
	trusted_from = (trusted_from_utc or day_start).astimezone(timezone.utc)

	accum: list[dict[str, list[float]]] = [
		{channel: [] for channel in CHANNELS} for _ in range(slots_per_day)
	]

	prev_ts: datetime | None = None
	for row in rows:
		cur_ts = _parse_ts_utc(row.get("ts_utc"))
		if cur_ts is None:
			continue
		if not _sample_is_trusted(row, prev_ts, trusted_from, poll_seconds):
			prev_ts = cur_ts
			continue

		slot_idx = int((cur_ts - day_start).total_seconds() // slot_seconds)
		if slot_idx < 0 or slot_idx >= slots_per_day:
			prev_ts = cur_ts
			continue

		powers = _stored_power_w(row)
		for channel, value in powers.items():
			accum[slot_idx][channel].append(float(value))
		prev_ts = cur_ts

	result: list[dict[str, Any]] = []
	for idx in range(slots_per_day):
		slot_ts = day_start.timestamp() + idx * slot_seconds
		slot_dt = datetime.fromtimestamp(slot_ts, tz=timezone.utc)
		point: dict[str, Any] = {
			"ts_utc": slot_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
			"slot_index": idx,
		}
		for channel in CHANNELS:
			values = accum[idx][channel]
			if len(values) >= min_samples_per_slot:
				point[f"{channel}_signed_w"] = round(sum(values) / len(values), 1)
				point[f"{channel}_sample_count"] = len(values)
			else:
				point[f"{channel}_signed_w"] = None
				point[f"{channel}_sample_count"] = len(values)
		result.append(point)
	return result


def _persisted_row_to_point(row: dict[str, Any]) -> dict[str, Any]:
	point: dict[str, Any] = {
		"ts_utc": str(row["slot_start_utc"]).replace("+00:00", "Z"),
		"slot_index": int(row["slot_index"]),
		"source": "power_slots",
	}
	for channel in CHANNELS:
		avg = row.get(f"{channel}_avg_w")
		count = int(row.get(f"{channel}_sample_count") or 0)
		point[f"{channel}_signed_w"] = round(float(avg), 1) if avg is not None else None
		point[f"{channel}_sample_count"] = count
	return point


def merge_persisted_chart_slots(
	live_slots: list[dict[str, Any]],
	persisted_rows: list[dict[str, Any]],
	current_slot_index: int,
) -> list[dict[str, Any]]:
	"""Prefer closed persisted slots; keep live aggregation for current slot."""
	by_index: dict[int, dict[str, Any]] = {}
	for row in persisted_rows:
		if int(row.get("quality_flag") or 0) != QUALITY_LIVE:
			continue
		by_index[int(row["slot_index"])] = _persisted_row_to_point(row)

	merged: list[dict[str, Any]] = []
	for live in live_slots:
		idx = int(live["slot_index"])
		if idx < current_slot_index and idx in by_index:
			merged.append(by_index[idx])
		else:
			out = dict(live)
			out["source"] = "live"
			merged.append(out)
	return merged


def current_slot_index(day_start_utc: datetime, slot_minutes: int, now: datetime | None = None) -> int:
	now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
	day_start = day_start_utc.astimezone(timezone.utc)
	slot_seconds = max(5, min(60, int(slot_minutes))) * 60
	idx = int((now - day_start).total_seconds() // slot_seconds)
	slots_per_day = (24 * 60) // max(5, min(60, int(slot_minutes)))
	return max(0, min(idx, slots_per_day - 1))
