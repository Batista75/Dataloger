#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="datalogger.service"
DB_FILE="$APP_DIR/data/measurements.db"
HEALTH_URL="http://127.0.0.1:8000/health"

ok() { echo "[ok] $*"; }
warn() { echo "[warn] $*"; }
crit() { echo "[crit] $*"; }

EXIT_CODE=0

if systemctl is-active --quiet "$SERVICE_NAME"; then
  ok "Service systemd actif"
else
  crit "Service systemd inactif"
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

if [ "$EXIT_CODE" -eq 0 ]; then
  ok "Diagnostic termine sans erreur"
fi

exit "$EXIT_CODE"
