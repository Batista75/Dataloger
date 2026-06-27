#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="datalogger.service"
SERVICE_TARGET="/etc/systemd/system/$SERVICE_NAME"
PURGE_DB="${1:-}"

info() { echo "[uninstall] $*"; }

info "Arret et suppression du service"
sudo systemctl disable --now "$SERVICE_NAME" >/dev/null 2>&1 || true
sudo rm -f "$SERVICE_TARGET"
sudo systemctl daemon-reload

if [ "$PURGE_DB" = "--purge-db" ]; then
  info "Suppression de la base locale"
  rm -f "$APP_DIR/data/measurements.db"
fi

info "Desinstallation terminee"
