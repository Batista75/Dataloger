#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="datalogger.service"
TUYA_SERVICE_NAME="datalogger-tuya.service"
DAY_EXPORT_TIMER_NAME="datalogger-day-export.timer"
DB_FILE="$APP_DIR/data/measurements.db"
TUYA_FILE="$APP_DIR/data/tuya_temperature_latest.json"
HEALTH_URL="http://127.0.0.1:8000/health"

ok() { echo "[ok] $*"; }
warn() { echo "[warn] $*"; }
crit() { echo "[crit] $*"; }

EXIT_CODE=0

if systemctl is-active --quiet "$SERVICE_NAME"; then
  ok "Service API systemd actif"
else
  crit "Service API systemd inactif"
  EXIT_CODE=2
fi

if [ -f "$DB_FILE" ]; then
  ok "Base SQLite detectee: $DB_FILE"
else
  crit "Base SQLite absente: $DB_FILE"
  EXIT_CODE=2
fi

if command -v curl >/dev/null 2>&1; then
  if curl -fsS "$HEALTH_URL" >/dev/null; then
    ok "Endpoint /health accessible"
  else
    crit "Endpoint /health inaccessible"
    EXIT_CODE=2
  fi
else
  warn "curl absent, verification HTTP ignoree"
fi

TUYA_ENABLED_RAW="$(grep -E '^TUYA_ENABLED=' "$APP_DIR/.env" 2>/dev/null | head -n1 | cut -d'=' -f2- | tr -d '[:space:]' || true)"
case "${TUYA_ENABLED_RAW,,}" in
  1|true|yes|on)
    if systemctl is-active --quiet "$TUYA_SERVICE_NAME"; then
      ok "Service Tuya systemd actif"
    else
      crit "Service Tuya systemd inactif"
      EXIT_CODE=2
    fi

    if [ -f "$TUYA_FILE" ]; then
      ok "Derniere mesure Tuya detectee: $TUYA_FILE"
    else
      warn "Fichier Tuya absent: $TUYA_FILE"
    fi
    ;;
  *)
    warn "TUYA_ENABLED!=1, checks Tuya ignores"
    ;;
esac

DAY_EXPORT_ENABLED_RAW="$(grep -E '^EM06_DAY_DATA_EXPORT_ENABLED=' "$APP_DIR/.env" 2>/dev/null | head -n1 | cut -d'=' -f2- | tr -d '[:space:]' || true)"
case "${DAY_EXPORT_ENABLED_RAW,,}" in
  1|true|yes|on)
    if systemctl is-active --quiet "$DAY_EXPORT_TIMER_NAME"; then
      ok "Timer export journalier actif"
    else
      crit "Timer export journalier inactif"
      EXIT_CODE=2
    fi
    ;;
  *)
    warn "EM06_DAY_DATA_EXPORT_ENABLED!=1, check timer ignore"
    ;;
esac

if [ "$EXIT_CODE" -eq 0 ]; then
  ok "Diagnostic termine sans erreur"
fi

exit "$EXIT_CODE"
