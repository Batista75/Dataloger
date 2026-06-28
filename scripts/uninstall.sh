#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="datalogger.service"
TUYA_SERVICE_NAME="datalogger-tuya.service"
DAY_EXPORT_SERVICE_NAME="datalogger-day-export.service"
DAY_EXPORT_TIMER_NAME="datalogger-day-export.timer"
SERVICE_TARGET="/etc/systemd/system/$SERVICE_NAME"
TUYA_SERVICE_TARGET="/etc/systemd/system/$TUYA_SERVICE_NAME"
DAY_EXPORT_SERVICE_TARGET="/etc/systemd/system/$DAY_EXPORT_SERVICE_NAME"
DAY_EXPORT_TIMER_TARGET="/etc/systemd/system/$DAY_EXPORT_TIMER_NAME"
PURGE_DB="${1:-}"

info() { echo "[uninstall] $*"; }

info "Arret et suppression des services"
sudo systemctl disable --now "$SERVICE_NAME" >/dev/null 2>&1 || true
sudo systemctl disable --now "$TUYA_SERVICE_NAME" >/dev/null 2>&1 || true
sudo systemctl disable --now "$DAY_EXPORT_TIMER_NAME" >/dev/null 2>&1 || true
sudo rm -f "$SERVICE_TARGET" "$TUYA_SERVICE_TARGET" "$DAY_EXPORT_SERVICE_TARGET" "$DAY_EXPORT_TIMER_TARGET"
sudo systemctl daemon-reload

if [ "$PURGE_DB" = "--purge-db" ]; then
  info "Suppression de la base locale"
  rm -f "$APP_DIR/data/measurements.db"
fi

info "Desinstallation terminee"
