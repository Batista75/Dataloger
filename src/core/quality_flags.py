"""Measurement quality_flag semantics."""

from __future__ import annotations

QUALITY_RAW = 0
QUALITY_LIVE = 1
QUALITY_IMPORTED_DAILY = 2
QUALITY_SUSPECT = 3


def is_trusted_live(quality_flag: int | None) -> bool:
	return int(quality_flag if quality_flag is not None else QUALITY_LIVE) == QUALITY_LIVE


def is_trusted_for_chart(quality_flag: int | None) -> bool:
	return is_trusted_live(quality_flag)


def is_trusted_for_energy_delta(quality_flag: int | None) -> bool:
	return is_trusted_live(quality_flag)
