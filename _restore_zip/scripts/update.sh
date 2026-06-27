#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="datalogger.service"

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

info "Redemarrage du service"
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl is-active --quiet "$SERVICE_NAME" || fail "Le service ne repond pas apres mise a jour"

info "Mise a jour terminee"
