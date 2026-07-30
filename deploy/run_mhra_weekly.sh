#!/usr/bin/env bash
# Weekly MHRA alerts and updates review, for the Hostinger VPS.
#
# Usage:
#   deploy/run_mhra_weekly.sh                          # 7 days ending today
#   deploy/run_mhra_weekly.sh --previous-week          # 7 days ending yesterday
#   deploy/run_mhra_weekly.sh --week-ending 2026-04-26
#   deploy/run_mhra_weekly.sh --days 21 --no-google
#
# Any additional flags are passed straight through to nice_guidance_monitor.mhra_cli.
#
# --previous-week exists because a window ending today is only complete at
# midnight. A scheduled 08:00 run whose window ends today cannot see anything
# published later that day, and the next window starts tomorrow, so those hours
# would never be reviewed. Ending yesterday keeps consecutive runs contiguous
# and entirely in the past.

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --previous-week)
      ARGS+=(--week-ending "$(date -d 'yesterday' '+%Y-%m-%d')")
      shift
      ;;
    *)
      ARGS+=("$1")
      shift
      ;;
  esac
done

take_lock "mhra-weekly"
load_env
resolve_python
prune_logs

LOG_FILE="$LOG_DIR/mhra-weekly-$(date '+%Y%m%dT%H%M%S').log"

log "Starting MHRA weekly review, logging to $LOG_FILE"
set +e
run_monitor nice_guidance_monitor.mhra_cli "${ARGS[@]}" 2>&1 | tee -a "$LOG_FILE"
STATUS=${PIPESTATUS[0]}
set -e

if [[ $STATUS -eq 0 ]]; then
  log "MHRA weekly review finished successfully"
else
  log "MHRA weekly review failed with exit code $STATUS; see $LOG_FILE"
fi
exit "$STATUS"
