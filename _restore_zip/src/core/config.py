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
    em06_namespace: str = os.getenv("EM06_NAMESPACE", "Appliance.Control.Electricity")
    em06_mqtt_host: str = os.getenv("EM06_MQTT_HOST", "")
    em06_mqtt_port: int = int(os.getenv("EM06_MQTT_PORT", "1883"))
    em06_mqtt_topic: str = os.getenv("EM06_MQTT_TOPIC", "")
    em06_mqtt_username: str = os.getenv("EM06_MQTT_USERNAME", "")
    em06_mqtt_password: str = os.getenv("EM06_MQTT_PASSWORD", "")
    refoss_port: int = int(os.getenv("REFOSS_PORT", "9989"))
    refoss_device_ip: str = os.getenv("REFOSS_DEVICE_IP", "")
    refoss_allow_simulated_fallback: bool = (
        os.getenv("REFOSS_ALLOW_SIMULATED_FALLBACK", "0").strip().lower() in {"1", "true", "yes", "on"}
    )


settings = Settings()
