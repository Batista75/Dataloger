#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_USER="${SUDO_USER:-$USER}"
SERVICE_NAME="datalogger-day-export.service"
TIMER_NAME="datalogger-day-export.timer"
SERVICE_TEMPLATE="$APP_DIR/systemd/datalogger-day-export.service.template"
TIMER_TEMPLATE="$APP_DIR/systemd/datalogger-day-export.timer.template"
SERVICE_TARGET="/etc/systemd/system/$SERVICE_NAME"
TIMER_TARGET="/etc/systemd/system/$TIMER_NAME"
ENV_FILE="$APP_DIR/.env"

info() { echo "[day-export-timer] $*"; }

if ! command -v sudo >/dev/null 2>&1; then
  echo "[day-export-timer][error] sudo requis" >&2
  exit 1
fi

if [ ! -f "$SERVICE_TEMPLATE" ] || [ ! -f "$TIMER_TEMPLATE" ]; then
  echo "[day-export-timer][error] templates systemd absents" >&2
  exit 1
fi

sed -e "s|__APP_DIR__|$APP_DIR|g" -e "s|__APP_USER__|$APP_USER|g" "$SERVICE_TEMPLATE" | sudo tee "$SERVICE_TARGET" >/dev/null
sed -e "s|__APP_DIR__|$APP_DIR|g" -e "s|__APP_USER__|$APP_USER|g" "$TIMER_TEMPLATE" | sudo tee "$TIMER_TARGET" >/dev/null
sudo systemctl daemon-reload

ENABLED_RAW=""
if [ -f "$ENV_FILE" ]; then
  ENABLED_RAW="$(grep -E '^EM06_DAY_DATA_EXPORT_ENABLED=' "$ENV_FILE" 2>/dev/null | head -n1 | cut -d'=' -f2- | tr -d '[:space:]' || true)"
fi

case "${ENABLED_RAW,,}" in
  1 | true | yes | on)
    info "Activation timer export journalier (00:05)"
    sudo systemctl enable --now "$TIMER_NAME"
    ;;
  *)
    info "Timer export desactive (EM06_DAY_DATA_EXPORT_ENABLED!=1)"
    sudo systemctl disable --now "$TIMER_NAME" >/dev/null 2>&1 || true
    ;;
esac
