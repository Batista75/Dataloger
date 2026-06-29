#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_USER="${SUDO_USER:-$USER}"
SERVICE_NAME="datalogger-maintenance.service"
TIMER_NAME="datalogger-maintenance.timer"
SERVICE_TEMPLATE="$APP_DIR/systemd/datalogger-maintenance.service.template"
TIMER_TEMPLATE="$APP_DIR/systemd/datalogger-maintenance.timer.template"
SERVICE_TARGET="/etc/systemd/system/$SERVICE_NAME"
TIMER_TARGET="/etc/systemd/system/$TIMER_NAME"
ENV_FILE="$APP_DIR/.env"

info() { echo "[maintenance-timer] $*"; }

if ! command -v sudo >/dev/null 2>&1; then
  echo "[maintenance-timer][error] sudo requis" >&2
  exit 1
fi

if [ ! -f "$SERVICE_TEMPLATE" ] || [ ! -f "$TIMER_TEMPLATE" ]; then
  echo "[maintenance-timer][error] templates systemd absents" >&2
  exit 1
fi

sed -e "s|__APP_DIR__|$APP_DIR|g" -e "s|__APP_USER__|$APP_USER|g" "$SERVICE_TEMPLATE" | sudo tee "$SERVICE_TARGET" >/dev/null
sed -e "s|__APP_DIR__|$APP_DIR|g" -e "s|__APP_USER__|$APP_USER|g" "$TIMER_TEMPLATE" | sudo tee "$TIMER_TARGET" >/dev/null
sudo systemctl daemon-reload

ENABLED_RAW=""
if [ -f "$ENV_FILE" ]; then
  ENABLED_RAW="$(grep -E '^MAINTENANCE_ENABLED=' "$ENV_FILE" 2>/dev/null | head -n1 | cut -d'=' -f2- | tr -d '[:space:]' || true)"
fi

case "${ENABLED_RAW,,}" in
  0 | false | no | off)
    info "Timer maintenance desactive (MAINTENANCE_ENABLED=0)"
    sudo systemctl disable --now "$TIMER_NAME" >/dev/null 2>&1 || true
    ;;
  *)
    info "Activation timer maintenance quotidien (02:30)"
    sudo systemctl enable --now "$TIMER_NAME"
    ;;
esac
