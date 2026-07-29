#!/usr/bin/env bash
# Shared helpers for the VPS runners. Sourced, not executed.

set -euo pipefail

APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_FILE="${SJC_CONFIG:-$APP_ROOT/config.json}"
LOG_DIR="${SJC_LOG_DIR:-$APP_ROOT/logs}"
LOCK_DIR="${SJC_LOCK_DIR:-$APP_ROOT/.locks}"
RUNTIME="${SJC_RUNTIME:-venv}"
LOG_RETENTION_DAYS="${SJC_LOG_RETENTION_DAYS:-90}"

cd "$APP_ROOT"
mkdir -p "$LOG_DIR" "$LOCK_DIR"

log() {
  printf '%s %s\n' "$(date --iso-8601=seconds)" "$*"
}

die() {
  log "ERROR: $*"
  exit 1
}

# Load secrets from .env without exporting comments or blank lines.
load_env() {
  local env_file="${SJC_ENV_FILE:-$APP_ROOT/.env}"
  if [[ -f "$env_file" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
    log "Loaded environment from $env_file"
  else
    log "No .env file at $env_file; relying on the ambient environment"
  fi
}

# Prefer the project virtualenv, then a local .deps directory, then system python.
resolve_python() {
  if [[ -x "$APP_ROOT/.venv/bin/python" ]]; then
    PYTHON="$APP_ROOT/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON="$(command -v python3)"
  else
    die "No python3 interpreter found"
  fi
  if [[ -d "$APP_ROOT/.deps" ]]; then
    export PYTHONPATH="$APP_ROOT/.deps${PYTHONPATH:+:$PYTHONPATH}"
  fi
  log "Using interpreter $PYTHON"
}

# Refuse to start a second copy of the same job rather than racing it.
take_lock() {
  local name="$1"
  exec 9>"$LOCK_DIR/$name.lock"
  if ! flock -n 9; then
    log "Another $name run holds the lock; exiting without running"
    exit 0
  fi
}

prune_logs() {
  find "$LOG_DIR" -type f -name '*.log' -mtime "+$LOG_RETENTION_DAYS" -delete 2>/dev/null || true
}

# Run the monitor either in the venv or inside the compose service.
run_monitor() {
  local module="$1"
  shift
  if [[ "$RUNTIME" == "docker" ]]; then
    log "Running $module via docker compose"
    docker compose -f "$APP_ROOT/deploy/docker-compose.yml" run --rm monitor \
      python -m "$module" --config "$(basename "$CONFIG_FILE")" "$@"
  else
    log "Running $module: $PYTHON -m $module --config $CONFIG_FILE $*"
    "$PYTHON" -m "$module" --config "$CONFIG_FILE" "$@"
  fi
}
