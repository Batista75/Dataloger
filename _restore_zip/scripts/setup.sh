#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="datalogger.service"
SERVICE_TEMPLATE="$APP_DIR/systemd/datalogger.service.template"
SERVICE_TARGET="/etc/systemd/system/$SERVICE_NAME"
APP_USER="${SUDO_USER:-$USER}"

info() { echo "[setup] $*"; }
fail() { echo "[setup][error] $*" >&2; exit 1; }

if ! command -v sudo >/dev/null 2>&1; then
  fail "sudo est requis pour l installation"
fi

info "Mise a jour des paquets systeme"
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip sqlite3 curl

info "Creation de l environnement virtuel"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

if [ ! -f "$APP_DIR/.env" ]; then
  info "Creation du fichier .env depuis .env.example"
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
fi

info "Initialisation de la base SQLite"
cd "$APP_DIR"
"$APP_DIR/.venv/bin/python" -m src.db.init_db

info "Installation du service systemd"
sed -e "s|__APP_DIR__|$APP_DIR|g" -e "s|__APP_USER__|$APP_USER|g" "$SERVICE_TEMPLATE" | sudo tee "$SERVICE_TARGET" >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"

if ! sudo systemctl is-active --quiet "$SERVICE_NAME"; then
  fail "Le service n a pas demarre correctement"
fi

IP_ADDR="$(hostname -I | awk '{print $1}')"
info "Installation terminee"
echo "URL locale: http://$IP_ADDR:8000"
echo "Test sante: http://$IP_ADDR:8000/health"
echo "Statut service: sudo systemctl status $SERVICE_NAME"
