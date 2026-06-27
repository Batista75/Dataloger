#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="datalogger.service"
TUYA_SERVICE_NAME="datalogger-tuya.service"

info() { echo "[update] $*"; }
fail() { echo "[update][error] $*" >&2; exit 1; }

if [ ! -d "$APP_DIR/.venv" ]; then
  fail "Environnement virtuel absent. Lance scripts/setup.sh d abord"
fi

info "Mise a jour des dependances Python"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

info "Mise a jour schema base"
cd "$APP_DIR"
"$APP_DIR/.venv/bin/python" -m src.db.init_db

info "Redemarrage du service API"
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl is-active --quiet "$SERVICE_NAME" || fail "Le service API ne repond pas apres mise a jour"

TUYA_ENABLED_RAW="$(grep -E '^TUYA_ENABLED=' "$APP_DIR/.env" 2>/dev/null | head -n1 | cut -d'=' -f2- | tr -d '[:space:]' || true)"
case "${TUYA_ENABLED_RAW,,}" in
  1|true|yes|on)
    info "Redemarrage du service Tuya"
    sudo systemctl enable --now "$TUYA_SERVICE_NAME"
    sudo systemctl restart "$TUYA_SERVICE_NAME"
    ;;
  *)
    info "Arret du service Tuya (TUYA_ENABLED!=1)"
    sudo systemctl disable --now "$TUYA_SERVICE_NAME" >/dev/null 2>&1 || true
    ;;
esac

info "Mise a jour terminee"
