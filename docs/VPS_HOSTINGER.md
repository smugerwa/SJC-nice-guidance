# Hostinger VPS Hosting

The automation runs on your own Hostinger VPS. The VPS owns both the schedule and
the run: systemd timers wake the job, the Python package does the retrieval and
analysis, and the reports are written to `outputs/` and to Google Drive. No
hosted automation platform is involved, and nothing has to stay signed in.

## What Runs, And When

| Job | Timer | Fires | Reviews |
| --- | --- | --- | --- |
| NICE guidance monthly review | `sjc-nice-monthly.timer` | Last day of each month, 17:00 | The calendar month that is ending |
| MHRA alerts weekly review | `sjc-mhra-weekly.timer` | Every Monday, 08:00 | The seven days ending the previous day |

Both timers name `Europe/London` in their own `OnCalendar` lines, so the schedule
follows GMT and BST without the installer touching the system clock. That matters
when the VPS also serves a website: changing the system timezone would shift
nginx, PHP and MySQL log timestamps too.

`OnCalendar=*-*~01` is systemd's "last day of the month", so no 28/29/30/31
guard is needed. `Persistent=true` means a month is caught up after a reboot
rather than skipped.

The weekly job reviews the seven days ending *yesterday*, via `--previous-week`.
A window ending today is only complete at midnight: an 08:00 run cannot see
anything published later that day, and the next window would start tomorrow, so
those hours would never be reviewed. Ending yesterday keeps consecutive runs
contiguous and entirely in the past.

A timezone inside `OnCalendar` needs systemd 252 or newer. Ubuntu 24.04 ships
255, so it works out of the box. On Ubuntu 22.04 (systemd 249) the installer
detects the older version, strips the suffix from the timers and sets the system
timezone to `Europe/London` instead, so the same `bash deploy/install.sh` works
on both. Override the timezone it picks with `TIMEZONE=...` if the box should
use something else.

## One-Time Setup

You need a Hostinger VPS running Ubuntu 22.04 or 24.04 and SSH access as root.
An existing web host is fine: the jobs open no ports, need no web server or
database, and live under `/opt` with their own system user, clear of any control
panel's stack. Take a snapshot first if the box is serving live sites.

```bash
ssh root@YOUR_VPS_IP

apt-get update && apt-get install -y git
git clone https://github.com/smugerwa/sjc-nice-guidance.git /root/sjc-nice-guidance
cd /root/sjc-nice-guidance
bash deploy/install.sh
```

`deploy/` only exists on branches that carry the VPS hosting layer. If
`bash: deploy/install.sh: No such file or directory` appears, the clone is on a
branch without it; `git checkout` the right branch and try again.

`install.sh` is safe to re-run. It:

- installs Python, `git`, `rsync` and `tzdata`
- leaves the system timezone alone unless you set `TIMEZONE`, or systemd is too
  old to carry a timezone in the timers
- creates the unprivileged `sjcguidance` service user
- syncs the project to `/opt/sjc-guidance`, never overwriting `.env`,
  `config.json`, `.google_token.json` or `outputs/`
- builds `/opt/sjc-guidance/.venv` and installs `requirements.txt`
- seeds `config.json` from `config.vps.json` and `.env` from `.env.example`
- installs and enables both systemd timers

Override the defaults if you want a different location or user:

```bash
APP_DIR=/srv/guidance APP_USER=guidance sudo -E bash deploy/install.sh
```

## Secrets

Secrets live only on the VPS, in `/opt/sjc-guidance/.env`, mode `600`, owned by
the service user. The systemd units read it through `EnvironmentFile=`.

```bash
sudo -u sjcguidance nano /opt/sjc-guidance/.env
```

```text
OPENAI_API_KEY=sk-...
SMTP_USERNAME=info@skinjointclinic.co.uk
SMTP_PASSWORD=...
```

Google Drive needs the OAuth token file. Generate it once on a machine with a
browser (see `docs/GOOGLE_CREDENTIALS.md`), then copy it across:

```bash
scp .google_token.json root@YOUR_VPS_IP:/tmp/.google_token.json
ssh root@YOUR_VPS_IP 'install -o sjcguidance -g sjcguidance -m 600 /tmp/.google_token.json /opt/sjc-guidance/.google_token.json && rm /tmp/.google_token.json'
```

The token refreshes itself on each run, so this is a one-time copy as long as
the refresh token stays valid.

## Practice Settings

```bash
sudo -u sjcguidance nano /opt/sjc-guidance/config.json
```

`config.json` is not committed. `config.vps.json` is the template it is seeded
from, and it already carries the Drive folder ID, notification address and
Office 365 SMTP host.

## Verify Before Trusting The Schedule

Offline smoke test, no network, no API keys, no Drive:

```bash
cd /opt/sjc-guidance
sudo -u sjcguidance ./deploy/run_monthly.sh --month "April 2026" \
  --sample-data data/sample_april_2026_sources.json --no-llm --no-google
```

Live run for one month, writing local files only:

```bash
sudo -u sjcguidance ./deploy/run_monthly.sh --month "April 2026" --no-google
```

Then a full run through the real timer path:

```bash
systemctl start sjc-nice-monthly.service
journalctl -u sjc-nice-monthly.service -n 60 --no-pager
```

Check what is scheduled next:

```bash
systemctl list-timers 'sjc-*'
```

## Running Jobs By Hand

```bash
cd /opt/sjc-guidance

# Monthly
sudo -u sjcguidance ./deploy/run_monthly.sh                        # config default month
sudo -u sjcguidance ./deploy/run_monthly.sh --current-month        # month in progress
sudo -u sjcguidance ./deploy/run_monthly.sh --month "2026-04"
sudo -u sjcguidance ./deploy/run_monthly.sh --no-google --no-llm

# Weekly MHRA
sudo -u sjcguidance ./deploy/run_mhra_weekly.sh                  # 7 days ending today
sudo -u sjcguidance ./deploy/run_mhra_weekly.sh --previous-week   # what the timer runs
sudo -u sjcguidance ./deploy/run_mhra_weekly.sh --week-ending 2026-04-26
sudo -u sjcguidance ./deploy/run_mhra_weekly.sh --days 21 --no-google
```

Unrecognised flags are passed through to the underlying CLI, so anything
`nice_guidance_monitor.cli` accepts works here too.

The runners take an exclusive `flock` per job. A second start while one is
already running exits quietly instead of racing it, which matters on the last
day of the month when a manual run and the timer can overlap.

## Where Output Lands

| Path | Contents |
| --- | --- |
| `/opt/sjc-guidance/outputs/<Month>/` | JSON source log, Markdown, HTML and DOCX |
| `/opt/sjc-guidance/outputs/MHRA/Week_ending_<date>/` | The weekly MHRA equivalents |
| `/opt/sjc-guidance/logs/` | One timestamped log per run, pruned after 90 days |
| Google Drive folder from `config.json` | The native Google Doc |
| `journalctl -u sjc-nice-monthly.service` | systemd's own record of each run |

The HTML file carries the same house style as the DOCX and Google Doc, so it can
be opened in a browser, printed to PDF, or served by nginx if you ever want the
reports on an internal URL.

## Updating The Deployment

```bash
cd /root/sjc-nice-guidance
git pull origin main
bash deploy/install.sh
```

The `rsync` step excludes secrets, `config.json` and `outputs/`, so an update
never disturbs live settings or past reports.

## Optional Container Route

If you would rather not install Python on the host, build the image and let the
same timers drive it. Scheduling stays with systemd either way.

```bash
cd /opt/sjc-guidance
docker compose -f deploy/docker-compose.yml build
SJC_RUNTIME=docker ./deploy/run_monthly.sh --current-month
```

To make the timers use the container permanently, add
`Environment=SJC_RUNTIME=docker` to both service units and
`systemctl daemon-reload`. The service user needs to be in the `docker` group.

## Runner Environment Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `SJC_CONFIG` | `<app>/config.json` | Config file to use |
| `SJC_ENV_FILE` | `<app>/.env` | Secrets file to source |
| `SJC_LOG_DIR` | `<app>/logs` | Where run logs are written |
| `SJC_LOG_RETENTION_DAYS` | `90` | Age at which logs are pruned |
| `SJC_RUNTIME` | `venv` | `venv` or `docker` |

## Troubleshooting

**A timer did not fire.** `systemctl list-timers 'sjc-*'` shows the next and last
run. Those times are displayed in the system timezone, so on a UTC box the
monthly run shows as 16:00 during BST and 17:00 during GMT. That is correct: the
timer itself is pinned to `Europe/London`.

**A timer will not load.** `systemctl status sjc-nice-monthly.timer` reporting an
invalid calendar means systemd is older than 252 and cannot parse the timezone
suffix. See the note under "What Runs, And When".

**A run failed.** `journalctl -u sjc-nice-monthly.service -n 100 --no-pager`, then
the matching file in `logs/`. The completion summary JSON is printed at the end
of every run and names each artefact.

**Email failed but the report was created.** `require_email_notification` is
`true`, so the run exits non-zero after printing the summary. The reports are
still in `outputs/` and Drive. See the SMTP notes in `docs/GITHUB_CLOUD.md`;
they apply unchanged on the VPS.

**Google Doc was skipped.** The run says why in the summary. Usually
`.google_token.json` is missing, unreadable by the service user, or its refresh
token has expired; regenerate it and copy it across again.

**Disk filling up.** `outputs/` grows by one folder per run and is never pruned
automatically, since the reports are the record. Logs are pruned after 90 days.

## Firewall

The jobs make only outbound HTTPS and SMTP connections. No inbound ports are
needed, so the Hostinger firewall can stay closed apart from SSH.
