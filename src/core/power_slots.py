"""Persist closed 15-minute power averages from trusted live measurements."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.core.chart_power import (
	GRAPH_CHANNELS,
	PARIS,
	build_chart_power_slots,
	resolve_trusted_chart_from,
	_parse_iso_date,
)
from src.core.config import Settings
from src.core.quality_flags import QUALITY_LIVE, QUALITY_SUSPECT
from src.db.repository import MeasurementRepository


def _parse_ts(value: str) -> datetime:
	return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _local_day_start_utc(ts: datetime) -> datetime:
	local = ts.astimezone(PARIS)
	start = local.replace(hour=0, minute=0, second=0, microsecond=0)
	return start.astimezone(timezone.utc)


def _slot_start_utc(ts: datetime, day_start: datetime, slot_minutes: int) -> datetime:
	slot_seconds = slot_minutes * 60
	day_start = day_start.astimezone(timezone.utc)
	idx = int((ts.astimezone(timezone.utc) - day_start).total_seconds() // slot_seconds)
	if idx < 0:
		idx = 0
	return day_start + timedelta(seconds=idx * slot_seconds)


def _trusted_settings(settings: Settings) -> dict[str, Any]:
	return {
		"unreliable_from": _parse_iso_date(settings.chart_unreliable_from),
		"unreliable_until": _parse_iso_date(settings.chart_unreliable_until),
		"local_start_hhmm": settings.chart_unreliable_local_start,
	}


def _slot_payload(
	slot_start: datetime,
	slot_minutes: int,
	slot_index: int,
	point: dict[str, Any],
) -> dict[str, Any]:
	payload: dict[str, Any] = {
		"slot_start_utc": slot_start.astimezone(timezone.utc).isoformat(),
		"slot_minutes": slot_minutes,
		"slot_index": slot_index,
		"quality_flag": QUALITY_LIVE,
	}
	for channel in GRAPH_CHANNELS:
		payload[f"{channel}_avg_w"] = point.get(f"{channel}_signed_w")
		payload[f"{channel}_sample_count"] = int(point.get(f"{channel}_sample_count") or 0)
	if payload["c1_sample_count"] < 1:
		payload["quality_flag"] = QUALITY_SUSPECT
	return payload


def commit_slot(
	repo: MeasurementRepository,
	settings: Settings,
	slot_start: datetime,
	slot_minutes: int | None = None,
) -> bool:
	slot_minutes = slot_minutes or settings.chart_slot_minutes
	slot_start = slot_start.astimezone(timezone.utc)
	slot_end = slot_start + timedelta(minutes=slot_minutes)
	day_start = _local_day_start_utc(slot_start)
	trusted_from = resolve_trusted_chart_from(day_start, **_trusted_settings(settings))

	if slot_end <= trusted_from:
		return False

	rows = repo.get_range_all(slot_start.isoformat(), slot_end.isoformat())
	if not rows:
		return False

	day_slots = build_chart_power_slots(
		rows,
		day_start_utc=day_start,
		slot_minutes=slot_minutes,
		trusted_from_utc=trusted_from,
		poll_seconds=settings.poll_seconds,
		min_samples_per_slot=settings.chart_min_samples_per_slot,
	)
	slot_index = int((slot_start - day_start).total_seconds() // (slot_minutes * 60))
	if slot_index < 0 or slot_index >= len(day_slots):
		return False

	point = day_slots[slot_index]
	if point.get("c1_signed_w") is None and point.get("a2_signed_w") is None:
		return False

	repo.upsert_power_slot(_slot_payload(slot_start, slot_minutes, slot_index, point))
	return True


def try_commit_closed_slots(repo: MeasurementRepository, settings: Settings) -> int:
	"""Finalize all fully elapsed slots not yet stored. Returns slots written."""
	slot_minutes = settings.chart_slot_minutes
	now = datetime.now(timezone.utc)
	slot_seconds = slot_minutes * 60
	day_start = _local_day_start_utc(now)
	current_slot_start = _slot_start_utc(now, day_start, slot_minutes)
	last_closed_start = current_slot_start - timedelta(seconds=slot_seconds)

	latest = repo.get_latest_power_slot_start(slot_minutes)
	if latest is None:
		trusted_from = resolve_trusted_chart_from(day_start, **_trusted_settings(settings))
		cursor = _slot_start_utc(trusted_from, day_start, slot_minutes)
	else:
		cursor = _parse_ts(latest) + timedelta(seconds=slot_seconds)

	committed = 0
	while cursor <= last_closed_start:
		if commit_slot(repo, settings, cursor, slot_minutes):
			committed += 1
		cursor += timedelta(seconds=slot_seconds)
	return committed


def backfill_power_slots_for_day(
	repo: MeasurementRepository,
	settings: Settings,
	day_start_utc: datetime | None = None,
) -> int:
	"""Backfill all closed slots for the local day (Paris midnight boundary)."""
	slot_minutes = settings.chart_slot_minutes
	slot_seconds = slot_minutes * 60
	now = datetime.now(timezone.utc)
	day_start = day_start_utc.astimezone(timezone.utc) if day_start_utc else _local_day_start_utc(now)
	current_slot_start = _slot_start_utc(now, day_start, slot_minutes)
	last_closed = current_slot_start - timedelta(seconds=slot_seconds)

	trusted_from = resolve_trusted_chart_from(day_start, **_trusted_settings(settings))
	cursor = day_start if trusted_from <= day_start else _slot_start_utc(trusted_from, day_start, slot_minutes)

	committed = 0
	while cursor <= last_closed:
		if commit_slot(repo, settings, cursor, slot_minutes):
			committed += 1
		cursor += timedelta(seconds=slot_seconds)
	return committed
