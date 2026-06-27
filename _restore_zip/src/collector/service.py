from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from src.collector.em06_client import EM06Client
from src.core.config import settings
from src.db.repository import MeasurementRepository


class CollectorService:
    def __init__(self, repo: MeasurementRepository) -> None:
        self.repo = repo
        self.client = EM06Client()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.sensor_state = "starting"
        self.last_error: str | None = None
        self.last_sample_ts_utc: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
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
                self.repo.insert_measurement(measurement)
                self.sensor_state = "connected"
                self.last_error = None
                self.last_sample_ts_utc = measurement.ts_utc
            except Exception as exc:  # noqa: BLE001
                self.sensor_state = "error"
                self.last_error = str(exc)
                now = datetime.now(timezone.utc).isoformat()
                self.repo.log_event("ERROR", "collector", self.last_error, now)
            self._stop_event.wait(interval)
