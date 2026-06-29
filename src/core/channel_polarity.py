"""Channel polarity correction (inverted probes)."""

from __future__ import annotations

from src.core.config import settings

CHANNELS = ("a1", "b1", "c1", "a2", "b2", "c2")


def inverted_channels() -> frozenset[str]:
	raw = str(getattr(settings, "c1_power_invert", "1") or "").strip().lower()
	if raw in {"1", "true", "yes", "on"}:
		return frozenset({"c1"})
	return frozenset()


def apply_channel_polarity(powers: dict[str, float]) -> dict[str, float]:
	inverted = inverted_channels()
	if not inverted:
		return powers
	out = dict(powers)
	for channel in inverted:
		if channel in out:
			out[channel] = -float(out[channel])
	return out
