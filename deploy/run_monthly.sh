#!/usr/bin/env bash
# Monthly NICE guidance governance review, for the Hostinger VPS.
#
# Usage:
#   deploy/run_monthly.sh                      # month from config default_target_month
#   deploy/run_monthly.sh --current-month      # calendar month in progress (last-day timer)
#   deploy/run_monthly.sh --month "April 2026"
#   deploy/run_monthly.sh --no-google --no-llm
#
# Any additional flags are passed straight through to nice_guidance_monitor.cli.

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

MONTH=""
CURRENT_MONTH=0
PASSTHROUGH=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --month)
      [[ $# -ge 2 ]] || die "--month needs a value, for example 'April 2026'"
      MONTH="$2"
      shift 2
      ;;
    --current-month)
      CURRENT_MONTH=1
      shift
      ;;
    *)
      PASSTHROUGH+=("$1")
      shift
      ;;
  esac
done

if [[ $CURRENT_MONTH -eq 1 && -z "$MONTH" ]]; then
  MONTH="$(date '+%B %Y')"
fi

take_lock "nice-monthly"
load_env
resolve_python
prune_logs

LOG_FILE="$LOG_DIR/nice-monthly-$(date '+%Y%m%dT%H%M%S').log"
ARGS=()
[[ -n "$MONTH" ]] && ARGS+=(--month "$MONTH")
[[ ${#PASSTHROUGH[@]} -gt 0 ]] && ARGS+=("${PASSTHROUGH[@]}")

log "Starting NICE monthly review${MONTH:+ for $MONTH}, logging to $LOG_FILE"
set +e
run_monitor nice_guidance_monitor.cli "${ARGS[@]}" 2>&1 | tee -a "$LOG_FILE"
STATUS=${PIPESTATUS[0]}
set -e

if [[ $STATUS -eq 0 ]]; then
  log "NICE monthly review finished successfully"
else
  log "NICE monthly review failed with exit code $STATUS; see $LOG_FILE"
fi
exit "$STATUS"
