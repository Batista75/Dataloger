#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="datalogger.service"
TUYA_SERVICE_NAME="datalogger-tuya.service"
SERVICE_TEMPLATE="$APP_DIR/systemd/datalogger.service.template"
TUYA_SERVICE_TEMPLATE="$APP_DIR/systemd/datalogger-tuya.service.template"
SERVICE_TARGET="/etc/systemd/system/$SERVICE_NAME"
TUYA_SERVICE_TARGET="/etc/systemd/system/$TUYA_SERVICE_NAME"
APP_USER="${SUDO_USER:-$USER}"

info() { echo "[setup] $*"; }
fail() { echo "[setup][error] $*" >&2; exit 1; }

if ! command -v sudo >/dev/null 2>&1; then
  fail "sudo est requis pour l installation"
fi

if [ ! -f "$SERVICE_TEMPLATE" ]; then
  fail "Template absent: $SERVICE_TEMPLATE"
fi

if [ ! -f "$TUYA_SERVICE_TEMPLATE" ]; then
  fail "Template absent: $TUYA_SERVICE_TEMPLATE"
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

info "Installation du service API systemd"
sed -e "s|__APP_DIR__|$APP_DIR|g" -e "s|__APP_USER__|$APP_USER|g" "$SERVICE_TEMPLATE" | sudo tee "$SERVICE_TARGET" >/dev/null

info "Installation du service Tuya systemd"
sed -e "s|__APP_DIR__|$APP_DIR|g" -e "s|__APP_USER__|$APP_USER|g" "$TUYA_SERVICE_TEMPLATE" | sudo tee "$TUYA_SERVICE_TARGET" >/dev/null

info "Installation du timer export journalier EM06"
chmod +x "$APP_DIR/scripts/export_em06_day_data.sh" "$APP_DIR/scripts/install_day_export_timer.sh"
"$APP_DIR/scripts/install_day_export_timer.sh"

sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"

TUYA_ENABLED_RAW="$(grep -E '^TUYA_ENABLED=' "$APP_DIR/.env" 2>/dev/null | head -n1 | cut -d'=' -f2- | tr -d '[:space:]' || true)"
case "${TUYA_ENABLED_RAW,,}" in
  1|true|yes|on)
    info "Activation du service Tuya (TUYA_ENABLED=1)"
    sudo systemctl enable --now "$TUYA_SERVICE_NAME"
    ;;
  *)
    info "Service Tuya non active (TUYA_ENABLED!=1)"
    sudo systemctl disable --now "$TUYA_SERVICE_NAME" >/dev/null 2>&1 || true
    ;;
esac

if ! sudo systemctl is-active --quiet "$SERVICE_NAME"; then
  fail "Le service API n a pas demarre correctement"
fi

IP_ADDR="$(hostname -I | awk '{print $1}')"
info "Installation terminee"
echo "URL locale: http://$IP_ADDR:8000"
echo "Test sante: http://$IP_ADDR:8000/health"
echo "Statut service API: sudo systemctl status $SERVICE_NAME"
echo "Statut service Tuya: sudo systemctl status $TUYA_SERVICE_NAME"
echo "Statut timer export: sudo systemctl status datalogger-day-export.timer"
