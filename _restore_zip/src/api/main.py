from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi import Query
from fastapi.staticfiles import StaticFiles

from src.collector.service import CollectorService
from src.core.config import settings
from src.db.init_db import init_database
from src.db.repository import MeasurementRepository

app = FastAPI(title="Datalogueur EM06", version="0.1.0")
repo = MeasurementRepository(settings.db_path)
collector = CollectorService(repo=repo)


@app.on_event("startup")
def startup_event() -> None:
    init_database()
    collector.start()


@app.on_event("shutdown")
def shutdown_event() -> None:
    collector.stop()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
def status() -> dict[str, str | int | None]:
    return {
        "server": "running",
        "sensor": collector.sensor_state,
        "last_error": collector.last_error,
        "last_sample_ts_utc": collector.last_sample_ts_utc,
        "poll_seconds": settings.poll_seconds,
        "em06_mode": settings.em06_mode,
        "ts_utc": datetime.now(timezone.utc).isoformat(),
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
            # Fresh if sample age is within 2 polling windows.
            is_fresh = age_seconds <= (settings.poll_seconds * 2)
        except ValueError:
            age_seconds = None
            is_fresh = None

    return {
        "data": latest,
        "data_age_seconds": age_seconds,
        "is_fresh": is_fresh,
        "ts_utc": datetime.now(timezone.utc).isoformat(),
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


# Serve static files (UI)
static_path = Path(__file__).parent.parent.parent / "static"
if static_path.exists():
    app.mount("/", StaticFiles(directory=str(static_path), html=True), name="static")
