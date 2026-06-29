"""Business energy metrics (C1 EDF reference + A2 PV)."""

from __future__ import annotations

from typing import Any


def deltas_from_indexes(
	c1_cons_min: float | None,
	c1_cons_max: float | None,
	c1_prod_min: float | None,
	c1_prod_max: float | None,
	a2_prod_min: float | None,
	a2_prod_max: float | None,
) -> tuple[float, float]:
	"""Return (c1_net_kwh, a2_production_kwh) from cumulative index min/max."""
	c1_import = max(0.0, _delta(c1_cons_min, c1_cons_max))
	c1_export = max(0.0, _delta(c1_prod_min, c1_prod_max))
	a2_prod = max(0.0, _delta(a2_prod_min, a2_prod_max))
	return round(c1_import - c1_export, 6), round(a2_prod, 6)


def compute_energy_metrics(c1_net_kwh: float, a2_prod_kwh: float) -> dict[str, Any]:
	"""Dashboard formulas: conso réelle, facturée, surplus, autoconso, rates."""
	c1 = float(c1_net_kwh)
	a2 = max(0.0, float(a2_prod_kwh))
	conso_reelle = c1 + a2
	conso_fact = max(0.0, c1)
	surplus = abs(c1) if c1 < 0 else 0.0
	autoconso = a2 - surplus
	taux_autoconso = (autoconso / a2 * 100.0) if a2 > 0 else None
	taux_autoproduction = (autoconso / conso_reelle * 100.0) if conso_reelle > 0 else None
	return {
		"c1_net_kwh": round(c1, 6),
		"a2_production_kwh": round(a2, 6),
		"conso_reelle_kwh": round(conso_reelle, 6),
		"conso_fact_kwh": round(conso_fact, 6),
		"surplus_kwh": round(surplus, 6),
		"autoconso_kwh": round(autoconso, 6),
		"taux_autoconso_pct": round(taux_autoconso, 3) if taux_autoconso is not None else None,
		"taux_autoproduction_pct": round(taux_autoproduction, 3) if taux_autoproduction is not None else None,
	}


def _delta(min_val: float | None, max_val: float | None) -> float:
	if min_val is None or max_val is None:
		return 0.0
	if max_val < min_val:
		return 0.0
	return float(max_val) - float(min_val)
