from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi import Query
from fastapi.staticfiles import StaticFiles
import requests
from requests.auth import HTTPDigestAuth

from src.collector.service import CollectorService
from src.core.chart_power_query import fetch_chart_power_for_day
from src.core.config import settings
from src.core.power_slots import backfill_power_slots_for_day, try_commit_closed_slots
from src.core.energy_metrics import compute_energy_metrics, deltas_from_indexes
from src.db.init_db import init_database
from src.db.repository import MeasurementRepository

CHANNEL_BY_ID = {
	1: "a1",
	2: "b1",
	3: "c1",
	4: "a2",
	5: "b2",
	6: "c2",
}

app = FastAPI(title="Datalogueur EM06P", version="0.1.0")
repo = MeasurementRepository(settings.db_path)
collector = CollectorService(repo=repo)


@app.on_event("startup")
def startup_event() -> None:
	init_database()
	if settings.chart_mark_suspect_on_startup:
		updated = repo.mark_suspect_measurements_before_trusted_cutoff(
			settings.chart_unreliable_from,
			settings.chart_unreliable_until,
			settings.chart_unreliable_local_start,
		)
		if updated:
			repo.log_event(
				"INFO",
				"quality",
				f"Marked {updated} measurements as suspect (quality_flag=3)",
				datetime.now(timezone.utc).isoformat(),
			)
	backfill_power_slots_for_day(repo, settings)
	collector.start()


@app.on_event("shutdown")
def shutdown_event() -> None:
	collector.stop()


@app.get("/health")
def health() -> dict[str, str]:
	return {"status": "ok"}


@app.get("/api/status")
def status() -> dict[str, str | int | bool | None]:
	return {
		"server": "running",
		"sensor": collector.sensor_state,
		"last_error": collector.last_error,
		"last_sample_ts_utc": collector.last_sample_ts_utc,
		"poll_seconds": settings.poll_seconds,
		"em06_mode": settings.em06_mode,
		"tuya_enabled": settings.tuya_enabled,
		"tuya_poll_seconds": settings.tuya_poll_seconds,
		"tuya_capture_mode": settings.tuya_capture_mode,
		"tuya_cloud_api_region": settings.tuya_cloud_api_region,
		"ts_utc": datetime.now(timezone.utc).isoformat(),
	}


@app.get("/api/temperature/latest")
def temperature_latest() -> dict[str, Any]:
	latest = _load_tuya_latest(settings.tuya_latest_json_path)
	age_seconds: float | None = None
	is_fresh: bool | None = None

	if isinstance(latest, dict) and isinstance(latest.get("ts_utc"), str):
		try:
			ts = datetime.fromisoformat(str(latest["ts_utc"]).replace("Z", "+00:00"))
			age_seconds = max((datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds(), 0.0)
			is_fresh = age_seconds <= max(settings.tuya_poll_seconds * 2, 60)
		except ValueError:
			age_seconds = None
			is_fresh = None

	return {
		"data": latest,
		"data_age_seconds": age_seconds,
		"is_fresh": is_fresh,
		"ts_utc": datetime.now(timezone.utc).isoformat(),
	}


@app.get("/api/temperature/history")
def temperature_history(
	from_ts_utc: str | None = None,
	to_ts_utc: str | None = None,
	minutes: int = 24 * 60,
	limit: int = 5000,
) -> dict[str, Any]:
	minutes = max(1, min(int(minutes), 43200))
	limit = max(1, min(int(limit), 20000))
	now = datetime.now(timezone.utc)
	if to_ts_utc is None:
		to_ts = now
	else:
		to_ts = datetime.fromisoformat(to_ts_utc.replace("Z", "+00:00")).astimezone(timezone.utc)

	if from_ts_utc is None:
		from_ts = to_ts - timedelta(minutes=minutes)
	else:
		from_ts = datetime.fromisoformat(from_ts_utc.replace("Z", "+00:00")).astimezone(timezone.utc)

	rows = _load_tuya_history(settings.tuya_history_csv_path, from_ts, to_ts, limit)
	return {
		"count": len(rows),
		"from_ts_utc": from_ts.isoformat(),
		"to_ts_utc": to_ts.isoformat(),
		"data": rows,
	}


@app.get("/api/measurements/latest")
def measurement_latest() -> dict[str, Any]:
	latest = repo.get_latest()
	age_seconds: float | None = None
	is_fresh: bool | None = None

	if latest and isinstance(latest.get("ts_utc"), str):
		try:
			ts = datetime.fromisoformat(str(latest["ts_utc"]).replace("Z", "+00:00"))
			age_seconds = max((datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds(), 0.0)
			is_fresh = age_seconds <= (settings.poll_seconds * 2)
		except ValueError:
			age_seconds = None
			is_fresh = None

	return {
		"data": latest,
		"channels_power_w": collector.get_channels_power_w(),
		"data_age_seconds": age_seconds,
		"is_fresh": is_fresh,
		"ts_utc": datetime.now(timezone.utc).isoformat(),
	}


@app.get("/api/energy/today")
def energy_today(
	from_ts_utc: str | None = Query(default=None, description="Local midnight as ISO UTC (browser)"),
) -> dict[str, Any]:
	now = datetime.now(timezone.utc)
	if from_ts_utc:
		try:
			from_ts = datetime.fromisoformat(from_ts_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
		except ValueError:
			from_ts = now.replace(hour=0, minute=0, second=0, microsecond=0)
	else:
		from_ts = now.replace(hour=0, minute=0, second=0, microsecond=0)

	raw = repo.get_energy_deltas_since(from_ts.isoformat())
	sample_count = int(raw.get("sample_count") or 0)
	c1_net, a2_prod = deltas_from_indexes(
		_to_float(raw.get("c1_cons_min")),
		_to_float(raw.get("c1_cons_max")),
		_to_float(raw.get("c1_prod_min")),
		_to_float(raw.get("c1_prod_max")),
		_to_float(raw.get("a2_prod_min")),
		_to_float(raw.get("a2_prod_max")),
	)
	metrics = compute_energy_metrics(c1_net, a2_prod)
	return {
		"from_ts_utc": from_ts.isoformat(),
		"generated_at_utc": now.isoformat(),
		"sample_count": sample_count,
		"first_ts_utc": raw.get("first_ts_utc"),
		"last_ts_utc": raw.get("last_ts_utc"),
		**metrics,
	}


@app.get("/api/measurements")
def measurements(
	from_ts_utc: str | None = Query(default=None),
	to_ts_utc: str | None = Query(default=None),
	minutes: int = Query(default=60, ge=1, le=43200),
	limit: int = Query(default=1000, ge=1, le=10000),
) -> dict[str, Any]:
	now = datetime.now(timezone.utc)
	if to_ts_utc is None:
		to_ts = now
	else:
		to_ts = datetime.fromisoformat(to_ts_utc.replace("Z", "+00:00"))
	if from_ts_utc is None:
		from_ts = to_ts - timedelta(minutes=minutes)
	else:
		from_ts = datetime.fromisoformat(from_ts_utc.replace("Z", "+00:00"))

	rows = repo.get_range(
		from_ts_utc=from_ts.astimezone(timezone.utc).isoformat(),
		to_ts_utc=to_ts.astimezone(timezone.utc).isoformat(),
		limit=limit,
	)
	return {
		"count": len(rows),
		"from_ts_utc": from_ts.astimezone(timezone.utc).isoformat(),
		"to_ts_utc": to_ts.astimezone(timezone.utc).isoformat(),
		"data": rows,
	}


@app.get("/api/measurements/chart-power")
def measurements_chart_power(
	from_ts_utc: str | None = Query(default=None, description="Local midnight as ISO UTC"),
	slot_minutes: int | None = Query(default=None, ge=5, le=60),
) -> dict[str, Any]:
	now = datetime.now(timezone.utc)
	if from_ts_utc:
		try:
			from_ts = datetime.fromisoformat(from_ts_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
		except ValueError:
			from_ts = now.replace(hour=0, minute=0, second=0, microsecond=0)
	else:
		from_ts = now.replace(hour=0, minute=0, second=0, microsecond=0)

	slot_min = slot_minutes or settings.chart_slot_minutes
	result = fetch_chart_power_for_day(repo, settings, from_ts, slot_minutes=slot_min)
	return result


@app.get("/api/quality/latest")
def quality_latest(minutes: int = Query(default=120, ge=30, le=1440)) -> dict[str, Any]:
	now = datetime.now(timezone.utc)
	from_ts = now - timedelta(minutes=minutes)
	expected_count = max(int((minutes * 60) / max(settings.poll_seconds, 1)), 1)
	sample_limit = min(max(expected_count // 4, 180), 400)
	rows = repo.get_recent_quality(limit=sample_limit)

	if not rows:
		return {
			"status": "manquante",
			"confidence_pct": 0,
			"rules": {
				"power_bounds_w": {"min": -6000, "max": 9000},
				"max_gap_seconds": max(settings.poll_seconds * 3, 30),
			},
			"indicators": {
				"window_minutes": minutes,
				"sample_count": 0,
				"missing_ratio_pct": 100.0,
				"gap_count": 0,
				"anomaly_count": 0,
				"quality_flag_suspect_count": 0,
			},
			"alerts": ["Aucune mesure recente"],
			"ui_behavior": {
				"show_warning_banner": True,
				"allow_strong_recommendation": False,
			},
			"known_limits": [
				"Qualite dependante de la disponibilite reseau capteur/API",
				"Evaluation basee sur les mesures recentes seulement",
			],
		}

	parsed_rows: list[tuple[datetime, dict[str, Any]]] = []
	for row in rows:
		ts = _parse_iso_utc(row.get("ts_utc"))
		if ts is None:
			continue
		if ts < from_ts or ts > now:
			continue
		parsed_rows.append((ts, row))

	parsed_rows.sort(key=lambda item: item[0])
	if not parsed_rows:
		return {
			"status": "invalide",
			"confidence_pct": 10,
			"rules": {
				"power_bounds_w": {"min": -6000, "max": 9000},
				"max_gap_seconds": max(settings.poll_seconds * 3, 30),
			},
			"indicators": {
				"window_minutes": minutes,
				"sample_count": 0,
				"missing_ratio_pct": 100.0,
				"gap_count": 0,
				"anomaly_count": 1,
				"quality_flag_suspect_count": 0,
			},
			"alerts": ["Horodatage invalide sur les mesures recentes"],
			"ui_behavior": {
				"show_warning_banner": True,
				"allow_strong_recommendation": False,
			},
			"known_limits": [
				"Source de temps capteur potentiellement desynchronisee",
			],
		}

	max_gap_seconds = max(settings.poll_seconds * 3, 30)
	actual_count = len(parsed_rows)
	missing_ratio_pct = max(0.0, 100.0 * (expected_count - actual_count) / expected_count)

	gap_count = 0
	suspect_count = 0
	quality_flag_suspect_count = 0

	prev = parsed_rows[0]
	for current in parsed_rows[1:]:
		delta = (current[0] - prev[0]).total_seconds()
		if delta > max_gap_seconds:
			gap_count += 1

		prev_cons = _to_float(prev[1].get("total_consumption_kwh")) or 0.0
		prev_prod = _to_float(prev[1].get("total_production_kwh")) or 0.0
		cur_cons = _to_float(current[1].get("total_consumption_kwh")) or 0.0
		cur_prod = _to_float(current[1].get("total_production_kwh")) or 0.0

		# Cumulative indexes should not go backwards significantly.
		if cur_cons + 1e-9 < prev_cons or cur_prod + 1e-9 < prev_prod:
			suspect_count += 1

		prev = current

	for _, row in parsed_rows:
		qf = row.get("quality_flag")
		try:
			if int(qf) != 1:
				quality_flag_suspect_count += 1
		except (TypeError, ValueError):
			quality_flag_suspect_count += 1

	alerts: list[str] = []
	if missing_ratio_pct > 20:
		alerts.append("Taux de mesures manquantes eleve")
	if gap_count > 0:
		alerts.append("Ruptures de collecte detectees")
	if suspect_count > 0:
		alerts.append("Incoherences d indexes cumulatifs detectees")
	if quality_flag_suspect_count > 0:
		alerts.append("Mesures marquees suspectes/invalide presentes")

	confidence = 100.0
	confidence -= min(missing_ratio_pct, 70)
	confidence -= min(gap_count * 8.0, 20)
	confidence -= min(suspect_count * 2.0, 20)
	confidence -= min(quality_flag_suspect_count * 1.0, 20)
	confidence = max(0.0, min(100.0, confidence))

	if confidence >= 80 and not alerts:
		status = "valide"
	elif confidence >= 45:
		status = "suspecte"
	else:
		status = "invalide"

	return {
		"status": status,
		"confidence_pct": int(round(confidence)),
		"rules": {
			"power_bounds_w": {"min": -6000, "max": 9000},
			"max_gap_seconds": max_gap_seconds,
		},
		"indicators": {
			"window_minutes": minutes,
			"sample_count": actual_count,
			"missing_ratio_pct": round(missing_ratio_pct, 2),
			"gap_count": gap_count,
			"anomaly_count": suspect_count,
			"quality_flag_suspect_count": quality_flag_suspect_count,
		},
		"alerts": alerts,
		"ui_behavior": {
			"show_warning_banner": bool(alerts),
			"allow_strong_recommendation": status == "valide",
		},
		"known_limits": [
			"La coherence multi-circuits reste partielle sans metadonnees metier completes",
			"La puissance instantanee derivee depend du pas de collecte",
		],
	}


@app.get("/api/history/daily-summary")
def history_daily_summary(days: int = Query(default=800, ge=60, le=3000)) -> dict[str, Any]:
	daily_rows = repo.get_daily_energy_summary(limit_days=days)
	series: list[dict[str, Any]] = []

	for row in daily_rows:
		day_raw = str(row.get("date_utc") or "")
		grid_import = _to_float(row.get("grid_import_kwh"))
		c1_net = _to_float(row.get("c1_net_kwh"))
		if not day_raw or grid_import is None or c1_net is None:
			continue
		try:
			day_obj = date.fromisoformat(day_raw)
		except ValueError:
			continue
		series.append(
			{
				"date": day_obj,
				"date_utc": day_raw,
				"grid_import_kwh": round(grid_import, 6),
				"grid_export_kwh": round(_to_float(row.get("grid_export_kwh")) or 0.0, 6),
				"pv_production_kwh": round(_to_float(row.get("pv_production_kwh")) or 0.0, 6),
				"c1_net_kwh": round(c1_net, 6),
				"autoconsumption_kwh": round(_to_float(row.get("autoconsumption_kwh")) or 0.0, 6),
				"autoconsumption_rate_pct": _to_float(row.get("autoconsumption_rate_pct")),
				# Backward-compatible alias: signed C1 net (EDF reference).
				"consumption_kwh": round(c1_net, 6),
			}
		)

	empty_payload: dict[str, Any] = {
		"refresh_policy": "daily",
		"energy_reference": "c1",
		"generated_day_utc": datetime.now(timezone.utc).date().isoformat(),
		"current_month_average_kwh": None,
		"last_day": None,
		"monthly_consumption_last_12": [],
		"monthly_pv_production_last_12": [],
		"daily_energy_series": [],
	}

	if not series:
		return empty_payload

	latest = series[-1]

	month_start = latest["date"].replace(day=1)
	month_values = [
		float(item["grid_import_kwh"])
		for item in series
		if item["date"] >= month_start and item["date"] <= latest["date"]
	]
	month_avg = sum(month_values) / len(month_values) if month_values else None

	monthly_import: dict[str, float] = {}
	monthly_pv: dict[str, float] = {}
	for item in series:
		month_key = item["date"].strftime("%Y-%m")
		monthly_import[month_key] = monthly_import.get(month_key, 0.0) + float(item["grid_import_kwh"])
		monthly_pv[month_key] = monthly_pv.get(month_key, 0.0) + float(item["pv_production_kwh"])

	sorted_months = sorted(monthly_import.keys())
	last_12 = sorted_months[-12:]
	monthly_payload = [
		{"month": month, "consumption_kwh": round(monthly_import[month], 6)}
		for month in last_12
	]
	monthly_pv_payload = [
		{"month": month, "pv_production_kwh": round(monthly_pv.get(month, 0.0), 6)}
		for month in last_12
	]

	daily_energy_series = [
		{
			"date_utc": item["date_utc"],
			"c1_net_kwh": item["c1_net_kwh"],
			"grid_import_kwh": item["grid_import_kwh"],
			"grid_export_kwh": item["grid_export_kwh"],
			"pv_production_kwh": item["pv_production_kwh"],
		}
		for item in series
	]

	return {
		"refresh_policy": "daily",
		"energy_reference": "c1",
		"generated_day_utc": datetime.now(timezone.utc).date().isoformat(),
		"current_month_average_kwh": round(month_avg, 6) if month_avg is not None else None,
		"last_day": {
			"day_utc": latest["date_utc"],
			"c1_net_kwh": latest["c1_net_kwh"],
			"grid_import_kwh": latest["grid_import_kwh"],
			"grid_export_kwh": latest["grid_export_kwh"],
			"pv_production_kwh": latest["pv_production_kwh"],
			"autoconsumption_kwh": latest["autoconsumption_kwh"],
			"autoconsumption_rate_pct": latest["autoconsumption_rate_pct"],
			"consumption_kwh": latest["c1_net_kwh"],
		},
		"monthly_consumption_last_12": monthly_payload,
		"monthly_pv_production_last_12": monthly_pv_payload,
		"daily_energy_series": daily_energy_series,
	}


@app.get("/api/refoss/compare-live")
def refoss_compare_live() -> dict[str, Any]:
	if settings.em06_mode != "refoss_local_socket":
		return {
			"enabled": False,
			"reason": "EM06_MODE is not refoss_local_socket",
		}

	try:
		base_url = settings.em06_http_url.strip()
		if not base_url:
			return {
				"enabled": True,
				"error": "EM06_HTTP_URL is empty",
			}
		if "://" not in base_url:
			base_url = f"http://{base_url}"
		parsed = urlparse(base_url)
		netloc = parsed.netloc or parsed.path
		rpc_url = f"{parsed.scheme or 'http'}://{netloc}/rpc/Em.Status.Get?id=65535"

		auth = None
		if settings.em06_http_username and settings.em06_http_password:
			auth = HTTPDigestAuth(settings.em06_http_username, settings.em06_http_password)

		resp = requests.get(rpc_url, timeout=max(settings.em06_timeout_seconds, 3), auth=auth)
		resp.raise_for_status()
		payload = resp.json()

		status = payload.get("result", payload)
		if isinstance(status, dict):
			status = status.get("status")
		entries = status if isinstance(status, list) else []
	except Exception as exc:
		return {
			"enabled": True,
			"error": f"RPC read failed: {exc}",
		}

	raw_power_w: dict[str, float] = {}
	for entry in entries:
		channel_id = int(_to_float(entry.get("id")) or 0)
		channel = CHANNEL_BY_ID.get(channel_id)
		if not channel:
			continue
		raw_power_w[channel] = float(_to_float(entry.get("power")) or 0.0)

	recent = repo.get_recent(limit=120)
	if len(recent) < 2:
		return {
			"enabled": True,
			"raw_power_w": raw_power_w,
			"error": "Not enough local samples to compute reconstructed power",
		}

	cur = recent[-1]
	prev = None
	for candidate in reversed(recent[:-1]):
		has_delta = False
		for channel in CHANNEL_BY_ID.values():
			cand_cons = _to_float(candidate.get(f"{channel}_consumption_kwh")) or 0.0
			cand_prod = _to_float(candidate.get(f"{channel}_production_kwh")) or 0.0
			cur_cons = _to_float(cur.get(f"{channel}_consumption_kwh")) or 0.0
			cur_prod = _to_float(cur.get(f"{channel}_production_kwh")) or 0.0
			if abs(cur_cons - cand_cons) > 1e-9 or abs(cur_prod - cand_prod) > 1e-9:
				has_delta = True
				break
		if has_delta:
			prev = candidate
			break

	if prev is None:
		prev = recent[-2]
	prev_ts = _parse_iso_utc(prev.get("ts_utc"))
	cur_ts = _parse_iso_utc(cur.get("ts_utc"))
	if prev_ts is None or cur_ts is None:
		return {
			"enabled": True,
			"raw_power_w": raw_power_w,
			"error": "Invalid local timestamps",
		}

	delta_s = max((cur_ts - prev_ts).total_seconds(), 1e-6)
	local_power_w: dict[str, float] = {}
	comparison: dict[str, Any] = {}

	for channel in CHANNEL_BY_ID.values():
		prev_cons = _to_float(prev.get(f"{channel}_consumption_kwh")) or 0.0
		cur_cons = _to_float(cur.get(f"{channel}_consumption_kwh")) or 0.0
		prev_prod = _to_float(prev.get(f"{channel}_production_kwh")) or 0.0
		cur_prod = _to_float(cur.get(f"{channel}_production_kwh")) or 0.0

		cons_w = max(0.0, (cur_cons - prev_cons) * 3600000.0 / delta_s)
		prod_w = max(0.0, (cur_prod - prev_prod) * 3600000.0 / delta_s)
		signed_local = cons_w - prod_w
		local_power_w[channel] = round(signed_local, 3)

		raw_value = float(raw_power_w.get(channel, 0.0))
		diff_w = signed_local - raw_value
		relative_pct = None
		if abs(raw_value) >= 1.0:
			relative_pct = round((diff_w / raw_value) * 100.0, 2)

		comparison[channel] = {
			"refoss_w": round(raw_value, 3),
			"local_w": round(signed_local, 3),
			"diff_w": round(diff_w, 3),
			"diff_pct": relative_pct,
		}

	raw_total = sum(raw_power_w.values())
	local_total = sum(local_power_w.values())
	total_diff = local_total - raw_total

	return {
		"enabled": True,
		"ts_utc": datetime.now(timezone.utc).isoformat(),
		"window_seconds": round(delta_s, 3),
		"comparison_by_channel": comparison,
		"totals": {
			"refoss_w": round(raw_total, 3),
			"local_w": round(local_total, 3),
			"diff_w": round(total_diff, 3),
			"diff_pct": round((total_diff / raw_total) * 100.0, 2) if abs(raw_total) >= 1.0 else None,
		},
	}


static_path = Path(__file__).parent.parent.parent / "static"
if static_path.exists():
	app.mount("/", StaticFiles(directory=str(static_path), html=True), name="static")


def _load_tuya_latest(path: Path) -> dict[str, Any] | None:
	if not path.exists():
		return None
	try:
		raw = json.loads(path.read_text(encoding="utf-8"))
	except (OSError, ValueError):
		return None
	if not isinstance(raw, dict):
		return None
	return raw


def _load_tuya_history(path: Path, from_ts: datetime, to_ts: datetime, limit: int) -> list[dict[str, Any]]:
	if not path.exists():
		return []

	rows: list[dict[str, Any]] = []
	try:
		with path.open("r", encoding="utf-8", newline="") as fh:
			reader = csv.DictReader(fh)
			for row in reader:
				extra = row.get(None)
				extra_list = extra if isinstance(extra, list) else []
				ts_raw = str(row.get("ts_utc", "") or "")
				if not ts_raw:
					continue
				try:
					ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).astimezone(timezone.utc)
				except ValueError:
					continue

				if ts < from_ts or ts > to_ts:
					continue

				temp = _to_float(row.get("temperature_c"))
				humidity = _to_float(row.get("humidity_pct"))
				source = str(row.get("source") or "").strip().lower()
				if source not in {"local", "cloud"} and extra_list:
					source = str(extra_list[-1] or "").strip().lower()
				if source not in {"local", "cloud"}:
					source = ""

				# Backward/transition compatibility: if humidity is missing but an old-row/new-row
				# mismatch occurred, humidity can end up in the dps_key slot.
				if humidity is None:
					humidity = _to_float(row.get("dps_key"))

				rows.append(
					{
						"ts_utc": ts_raw,
						"temperature_c": temp,
						"humidity_pct": humidity,
						"device_id": row.get("device_id"),
						"device_ip": row.get("device_ip"),
						"device_mac": row.get("device_mac"),
						"source": source or None,
					}
				)
	except OSError:
		return []

	rows.sort(key=lambda item: str(item.get("ts_utc", "")))
	if len(rows) > limit:
		rows = rows[-limit:]
	return rows


def _to_float(value: Any) -> float | None:
	if value in (None, ""):
		return None
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def _parse_iso_utc(value: Any) -> datetime | None:
	if not isinstance(value, str) or not value.strip():
		return None
	try:
		return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
	except ValueError:
		return None
