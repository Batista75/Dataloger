#!/usr/bin/env bash
# Nightly export: Refoss-compatible Power Monitor Day Data CSV from SQLite.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$APP_DIR/.env"
PYTHON="$APP_DIR/.venv/bin/python"
EXPORT_TOOL="$APP_DIR/tools/export_em06_day_data.py"

log() { echo "[day-export] $*"; }

read_env() {
  local key="$1"
  local default_value="${2:-}"
  if [ ! -f "$ENV_FILE" ]; then
    echo "$default_value"
    return
  fi
  local raw
  raw="$(grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | head -n1 | cut -d'=' -f2- || true)"
  if [ -z "$raw" ]; then
    echo "$default_value"
  else
    # Strip CR/LF/spaces (Windows .env or CRLF scripts on Linux).
    echo "$raw" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
  fi
}

is_truthy() {
  case "${1,,}" in
    1 | true | yes | on) return 0 ;;
    *) return 1 ;;
  esac
}

if [ ! -x "$PYTHON" ]; then
  log "error: virtualenv Python introuvable ($PYTHON)"
  exit 1
fi

if [ ! -f "$EXPORT_TOOL" ]; then
  log "error: outil absent ($EXPORT_TOOL)"
  exit 1
fi

DB_PATH="$(read_env DB_PATH "data/measurements.db")"
OUTPUT_DIR="$(read_env EM06_DAY_DATA_OUTPUT_DIR "exports")"
EXTENSION_OUT="$(read_env EM06_DAY_DATA_EXTENSION_OUT "exports/Power Monitor Day Data - raspberry.csv")"
COMBINED_OUT="$(read_env EM06_DAY_DATA_COMBINED_OUT "exports/Power Monitor Day Data - combined.csv")"
BASE_CSV="$(read_env EM06_DAY_DATA_BASE_CSV "")"
FROM_DATE="$(read_env EM06_DAY_DATA_FROM_DATE "")"

if [[ "$DB_PATH" != /* ]]; then
  DB_PATH="$APP_DIR/$DB_PATH"
fi
if [[ "$OUTPUT_DIR" != /* ]]; then
  OUTPUT_DIR="$APP_DIR/$OUTPUT_DIR"
fi
if [[ "$EXTENSION_OUT" != /* ]]; then
  EXTENSION_OUT="$APP_DIR/$EXTENSION_OUT"
fi
if [[ "$COMBINED_OUT" != /* ]]; then
  COMBINED_OUT="$APP_DIR/$COMBINED_OUT"
fi
if [ -n "$BASE_CSV" ] && [[ "$BASE_CSV" != /* ]]; then
  BASE_CSV="$APP_DIR/$BASE_CSV"
fi

mkdir -p "$OUTPUT_DIR"
mkdir -p "$(dirname "$EXTENSION_OUT")"
mkdir -p "$(dirname "$COMBINED_OUT")"

CMD=(
  "$PYTHON" "$EXPORT_TOOL"
  --db "$DB_PATH"
  --out "$EXTENSION_OUT"
)

if [ -n "$FROM_DATE" ]; then
  CMD+=(--from-date "$FROM_DATE")
fi

if [ -n "$BASE_CSV" ] && [ -f "$BASE_CSV" ]; then
  CMD+=(--merge-with "$BASE_CSV" --merge-out "$COMBINED_OUT")
  log "Export + fusion avec $BASE_CSV"
elif [ -n "$BASE_CSV" ]; then
  log "warn: historique Refoss introuvable ($BASE_CSV), export Raspberry seul"
  log "Export Raspberry seul"
else
  log "Export Raspberry seul (EM06_DAY_DATA_BASE_CSV non configure)"
fi

log "Demarrage: ${CMD[*]}"
"${CMD[@]}"
log "Termine"
