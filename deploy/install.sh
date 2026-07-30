#!/usr/bin/env bash
# Provision this project on a fresh Hostinger VPS (Ubuntu 22.04 or 24.04).
#
# Run as root from a clone of the repository:
#   sudo bash deploy/install.sh
#
# Override the defaults with environment variables:
#   APP_DIR=/srv/guidance APP_USER=guidance sudo -E bash deploy/install.sh
#
# The system timezone is left alone by default, since this may be a shared host
# running a website: the timers carry Europe/London in their own schedules. Set
# TIMEZONE explicitly only if you want the whole box changed, which is needed on
# systemd older than 252 (Ubuntu 22.04) where timers cannot name a timezone:
#   TIMEZONE=Europe/London sudo -E bash deploy/install.sh

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/sjc-guidance}"
APP_USER="${APP_USER:-sjcguidance}"
TIMEZONE="${TIMEZONE:-}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run this script as root: sudo bash deploy/install.sh" >&2
  exit 1
fi

echo "==> Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git ca-certificates tzdata rsync

# A timezone inside OnCalendar needs systemd 252+. Older releases (Ubuntu 22.04
# ships 249) cannot parse it and would refuse to load the timers, so on those the
# suffix is stripped below and the system timezone is set instead.
SYSTEMD_VERSION="$(systemctl --version 2>/dev/null | head -1 | awk '{print $2}')"
STRIP_TIMER_TIMEZONE=0
if [[ "$SYSTEMD_VERSION" =~ ^[0-9]+$ ]] && (( SYSTEMD_VERSION < 252 )); then
  STRIP_TIMER_TIMEZONE=1
  echo "==> systemd $SYSTEMD_VERSION cannot parse a timezone in OnCalendar"
  echo "    Removing the suffix from the timers and using the system timezone instead."
  TIMEZONE="${TIMEZONE:-Europe/London}"
fi

if [[ -n "$TIMEZONE" ]]; then
  echo "==> Setting the system timezone to $TIMEZONE"
  timedatectl set-timezone "$TIMEZONE" || echo "    Could not set the timezone; leaving it unchanged."
else
  echo "==> Leaving the system timezone unchanged ($(timedatectl show -p Timezone --value 2>/dev/null || echo unknown))"
  echo "    The timers name Europe/London in their own schedules."
fi

if ! id -u "$APP_USER" >/dev/null 2>&1; then
  echo "==> Creating service user $APP_USER"
  useradd --system --create-home --home-dir "/home/$APP_USER" --shell /usr/sbin/nologin "$APP_USER"
fi

echo "==> Syncing the project into $APP_DIR"
mkdir -p "$APP_DIR"
if [[ "$SOURCE_DIR" != "$APP_DIR" ]]; then
  # Never overwrite live secrets, config or generated reports.
  rsync -a --delete \
    --exclude '.git/' \
    --exclude '.venv/' \
    --exclude '.deps/' \
    --exclude 'outputs/' \
    --exclude 'logs/' \
    --exclude '.locks/' \
    --exclude '.env' \
    --exclude 'config.json' \
    --exclude '.google_token.json' \
    "$SOURCE_DIR"/ "$APP_DIR"/
fi
mkdir -p "$APP_DIR/outputs" "$APP_DIR/logs" "$APP_DIR/.locks"

echo "==> Creating the virtualenv and installing dependencies"
if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
  python3 -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip --quiet
"$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt" --quiet

if [[ ! -f "$APP_DIR/config.json" ]]; then
  echo "==> Seeding config.json from config.vps.json"
  cp "$APP_DIR/config.vps.json" "$APP_DIR/config.json"
fi

if [[ ! -f "$APP_DIR/.env" ]]; then
  echo "==> Seeding .env from .env.example (fill in the secrets before the first run)"
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
fi

chmod +x "$APP_DIR"/deploy/*.sh
chmod 600 "$APP_DIR/.env"
[[ -f "$APP_DIR/.google_token.json" ]] && chmod 600 "$APP_DIR/.google_token.json"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "==> Installing systemd units"
for unit in "$APP_DIR"/deploy/systemd/*.service "$APP_DIR"/deploy/systemd/*.timer; do
  name="$(basename "$unit")"
  sed_args=(-e "s#/opt/sjc-guidance#$APP_DIR#g" -e "s#sjcguidance#$APP_USER#g")
  if [[ $STRIP_TIMER_TIMEZONE -eq 1 ]]; then
    sed_args+=(-e "s#^\(OnCalendar=.*\) Europe/London\$#\1#")
  fi
  sed "${sed_args[@]}" "$unit" > "/etc/systemd/system/$name"
done

systemctl daemon-reload
systemctl enable --now sjc-nice-monthly.timer sjc-mhra-weekly.timer

cat <<EOF

Done. Next steps:

  1. Add your secrets:            sudo -u $APP_USER nano $APP_DIR/.env
  2. Check the practice settings: sudo -u $APP_USER nano $APP_DIR/config.json
  3. Copy the Google token over:  sudo install -o $APP_USER -g $APP_USER -m 600 .google_token.json $APP_DIR/.google_token.json
  4. Offline smoke test:
       sudo -u $APP_USER $APP_DIR/deploy/run_monthly.sh --month "April 2026" \\
         --sample-data data/sample_april_2026_sources.json --no-llm --no-google
  5. Confirm the schedule:        systemctl list-timers 'sjc-*'

EOF
