"""Shared chart-power query: prefer power_slots, live raw only for open slot."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.core.chart_power import (
	build_chart_power_slots,
	current_slot_index,
	merge_persisted_chart_slots,
	resolve_trusted_chart_from,
	_parse_iso_date,
)
from src.core.config import Settings
from src.db.repository import MeasurementRepository


def _slots_per_day(slot_minutes: int) -> int:
	return (24 * 60) // max(5, min(60, int(slot_minutes)))


def fetch_chart_power_for_day(
	repo: MeasurementRepository,
	settings: Settings,
	from_ts_utc: datetime,
	now: datetime | None = None,
	slot_minutes: int | None = None,
) -> dict[str, Any]:
	now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
	from_ts = from_ts_utc.astimezone(timezone.utc)
	slot_min = slot_minutes or settings.chart_slot_minutes
	trusted_from = resolve_trusted_chart_from(
		from_ts,
		unreliable_from=_parse_iso_date(settings.chart_unreliable_from),
		unreliable_until=_parse_iso_date(settings.chart_unreliable_until),
		local_start_hhmm=settings.chart_unreliable_local_start,
	)
	day_end = from_ts + timedelta(days=1)
	persisted = repo.get_power_slots_for_day(from_ts.isoformat(), day_end.isoformat(), slot_min)
	day_complete = now >= day_end

	if day_complete:
		cur_idx = _slots_per_day(slot_min)
		rows: list[dict[str, Any]] = []
	elif persisted:
		slot_seconds = max(5, min(60, slot_min)) * 60
		cur_idx = current_slot_index(from_ts, slot_min, now)
		live_from = from_ts + timedelta(seconds=cur_idx * slot_seconds)
		rows = repo.get_range_all(live_from.isoformat(), now.isoformat())
	else:
		cur_idx = current_slot_index(from_ts, slot_min, now)
		rows = repo.get_range_all(from_ts.isoformat(), now.isoformat())

	live_slots = build_chart_power_slots(
		rows,
		day_start_utc=from_ts,
		slot_minutes=slot_min,
		trusted_from_utc=trusted_from,
		poll_seconds=settings.poll_seconds,
		min_samples_per_slot=settings.chart_min_samples_per_slot,
	)

	if persisted:
		slots = merge_persisted_chart_slots(live_slots, persisted, cur_idx)
		if day_complete:
			power_source = "power_slots"
		else:
			power_source = "power_slots+live"
	else:
		slots = live_slots
		power_source = "stored_power_w"

	return {
		"from_ts_utc": from_ts.isoformat(),
		"to_ts_utc": now.isoformat(),
		"trusted_from_utc": trusted_from.isoformat(),
		"power_source": power_source,
		"persisted_slot_count": len(persisted),
		"sample_count": len(rows),
		"slot_minutes": slot_min,
		"data": slots,
	}
