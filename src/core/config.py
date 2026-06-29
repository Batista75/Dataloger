from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
	app_host: str = os.getenv("APP_HOST", "0.0.0.0")
	app_port: int = int(os.getenv("APP_PORT", "8000"))
	poll_seconds: int = int(os.getenv("POLL_SECONDS", "3"))
	db_path: Path = Path(os.getenv("DB_PATH", "data/measurements.db"))
	em06_mode: str = os.getenv("EM06_MODE", "mock")
	em06_http_url: str = os.getenv("EM06_HTTP_URL", "")
	em06_timeout_seconds: int = int(os.getenv("EM06_TIMEOUT_SECONDS", "5"))
	em06_http_username: str = os.getenv("EM06_HTTP_USERNAME", os.getenv("ADMIN_USERNAME", "admin"))
	em06_http_password: str = os.getenv("EM06_HTTP_PASSWORD", os.getenv("ADMIN_PASSWORD", ""))
	em06_meross_key: str = os.getenv("EM06_MEROSS_KEY", "")
	em06_namespace: str = os.getenv("EM06_NAMESPACE", "Appliance.Control.Electricity")
	em06_mqtt_host: str = os.getenv("EM06_MQTT_HOST", "")
	em06_mqtt_port: int = int(os.getenv("EM06_MQTT_PORT", "1883"))
	em06_mqtt_topic: str = os.getenv("EM06_MQTT_TOPIC", "")
	em06_mqtt_client_id: str = os.getenv("EM06_MQTT_CLIENT_ID", "")
	em06_mqtt_username: str = os.getenv("EM06_MQTT_USERNAME", "")
	em06_mqtt_password: str = os.getenv("EM06_MQTT_PASSWORD", "")
	refoss_port: int = int(os.getenv("REFOSS_PORT", "9989"))
	refoss_device_ip: str = os.getenv("REFOSS_DEVICE_IP", "")
	refoss_allow_simulated_fallback: bool = (
		os.getenv("REFOSS_ALLOW_SIMULATED_FALLBACK", "0").strip().lower() in {"1", "true", "yes", "on"}
	)
	tuya_enabled: bool = os.getenv("TUYA_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
	tuya_poll_seconds: int = int(os.getenv("TUYA_POLL_SECONDS", "30"))
	tuya_target_macs: str = os.getenv("TUYA_TARGET_MACS", "")
	tuya_tinytuya_device_id: str = os.getenv("TUYA_TINYTUYA_DEVICE_ID", "")
	tuya_tinytuya_local_key: str = os.getenv("TUYA_TINYTUYA_LOCAL_KEY", "")
	tuya_tinytuya_ip: str = os.getenv("TUYA_TINYTUYA_IP", "")
	tuya_tinytuya_version: str = os.getenv("TUYA_TINYTUYA_VERSION", "3.3")
	tuya_capture_mode: str = os.getenv("TUYA_CAPTURE_MODE", "local")
	tuya_cloud_api_region: str = os.getenv("TUYA_CLOUD_API_REGION", "eu")
	tuya_latest_json_path: Path = Path(os.getenv("TUYA_LATEST_JSON_PATH", "data/tuya_temperature_latest.json"))
	tuya_history_csv_path: Path = Path(os.getenv("TUYA_HISTORY_CSV_PATH", "data/tuya_temperature_history.csv"))
	c1_power_invert: str = os.getenv("C1_POWER_INVERT", "0")
	chart_slot_minutes: int = int(os.getenv("CHART_SLOT_MINUTES", "15"))
	chart_unreliable_from: str = os.getenv("CHART_UNRELIABLE_FROM", "2026-06-27")
	chart_unreliable_until: str = os.getenv("CHART_UNRELIABLE_UNTIL", "2026-06-29")
	chart_unreliable_local_start: str = os.getenv("CHART_UNRELIABLE_LOCAL_START", "14:00")
	chart_min_samples_per_slot: int = int(os.getenv("CHART_MIN_SAMPLES_PER_SLOT", "5"))
	chart_mark_suspect_on_startup: bool = (
		os.getenv("CHART_MARK_SUSPECT_ON_STARTUP", "0").strip().lower() in {"1", "true", "yes", "on"}
	)
	raw_retention_days: int = int(os.getenv("RAW_RETENTION_DAYS", "90"))
	backup_dir: Path = Path(os.getenv("BACKUP_DIR", "data/backups"))
	backup_keep_count: int = int(os.getenv("BACKUP_KEEP_COUNT", "14"))
	maintenance_enabled: bool = (
		os.getenv("MAINTENANCE_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
	)


settings = Settings()
