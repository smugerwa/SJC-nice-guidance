#!/usr/bin/env bash
# Weekly MHRA alerts and updates review, for the Hostinger VPS.
#
# Usage:
#   deploy/run_mhra_weekly.sh                          # 7 days ending today
#   deploy/run_mhra_weekly.sh --week-ending 2026-04-26
#   deploy/run_mhra_weekly.sh --days 21 --no-google
#
# Any additional flags are passed straight through to nice_guidance_monitor.mhra_cli.

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

take_lock "mhra-weekly"
load_env
resolve_python
prune_logs

LOG_FILE="$LOG_DIR/mhra-weekly-$(date '+%Y%m%dT%H%M%S').log"

log "Starting MHRA weekly review, logging to $LOG_FILE"
set +e
run_monitor nice_guidance_monitor.mhra_cli "$@" 2>&1 | tee -a "$LOG_FILE"
STATUS=${PIPESTATUS[0]}
set -e

if [[ $STATUS -eq 0 ]]; then
  log "MHRA weekly review finished successfully"
else
  log "MHRA weekly review failed with exit code $STATUS; see $LOG_FILE"
fi
exit "$STATUS"
