# NICE Guidance Monthly Review Automation

This workflow creates a monthly clinical-governance report for NICE guidance that was published or updated in a target month. It is designed for a UK general practice or private primary care clinic and uses NICE guidance pages as the source of truth.

It is self-hosted: the automation runs on a Hostinger VPS, scheduled by systemd timers, with no hosted automation platform in the loop. Setup is documented in `docs/VPS_HOSTINGER.md`.

## Where It Runs

| Job | Timer | Fires |
| --- | --- | --- |
| NICE guidance monthly review | `sjc-nice-monthly.timer` | Last day of each month, 17:00 |
| MHRA alerts weekly review | `sjc-mhra-weekly.timer` | Every Monday, 08:00 |

The GitHub Actions workflow is retained for manual runs only, as a fallback when the VPS is unavailable. It is not scheduled, so it cannot double-run against the VPS timers.

## What It Produces

- A structured source log as JSON.
- A Markdown report for easy review or fallback use.
- A print-ready HTML report in the practice house style, for browser review, printing to PDF or serving from the VPS.
- A headed-paper DOCX using the configured clinic template where available.
- A native Google Doc created directly in the configured Google Drive folder when Google credentials are available.
- The native Google Doc is generated from the structured report data, not from a DOCX upload, and uses real Google Docs tables for dashboards and appendices.

## Document House Style

DOCX, HTML and Google Doc output share one house style, defined in `nice_guidance_monitor/house_style.py`:

- A navy title over a hairline rule, a mid-blue descriptive subtitle and a bold practice line.
- Mid-blue section headings, each preceded by a full-width hairline, with navy sub-headings beneath.
- A borderless metadata table with alternating pale-blue banding and bold navy labels.
- Data tables with a shaded header, banded rows and faint row rules instead of a full grid.
- Calibri throughout, blue bullet and number glyphs, and a small grey footer carrying the document label and page number.

Edit the constants at the top of `house_style.py` to retune colours, fonts or sizes; all three renderers follow.

## Files To Edit

Edit `config.json`:

- `practice_name`: clinic or practice name.
- `reviewer`: named reviewer or role.
- `headed_paper_template_docx`: local DOCX headed-paper template.
- `destination_drive_folder_id`: Google Drive folder ID for completed reports.
- `email_notification`: email address for the monthly completion alert.
- `smtp`: optional SMTP settings for completion notifications.
- `thresholds`: scoring cut-offs for high/very high relevance.
- `llm.model`: model used for clinical-governance analysis.

Set secrets in `.env` or your shell:

- `OPENAI_API_KEY`: enables full structured clinical analysis.
- `GOOGLE_APPLICATION_CREDENTIALS`: path to a Google service-account JSON file for creating the native Google Doc in Drive.
- `SMTP_USERNAME` and `SMTP_PASSWORD`: optional SMTP login for completion emails.

On the VPS these live in `/opt/sjc-guidance/.env`, mode `600`, read by the systemd units through `EnvironmentFile=`. SMTP is optional and can remain blank.

Google Drive setup is documented in `docs/GOOGLE_CREDENTIALS.md`.

VPS hosting and scheduling are documented in `docs/VPS_HOSTINGER.md`.

GitHub Actions fallback setup is documented in `docs/GITHUB_CLOUD.md`.

## Install On The VPS

From a clone on the VPS, as root:

```bash
bash deploy/install.sh
```

This installs Python, creates the `sjcguidance` service user, syncs the project to `/opt/sjc-guidance`, builds a virtualenv, seeds `config.json` and `.env`, and enables both timers. It is safe to re-run and never overwrites secrets, config or past reports. Full detail, including the container route, is in `docs/VPS_HOSTINGER.md`.

## Run On The VPS

```bash
cd /opt/sjc-guidance

sudo -u sjcguidance ./deploy/run_monthly.sh --current-month
sudo -u sjcguidance ./deploy/run_monthly.sh --month "April 2026" --no-google
sudo -u sjcguidance ./deploy/run_mhra_weekly.sh
sudo -u sjcguidance ./deploy/run_mhra_weekly.sh --week-ending 2026-04-26

systemctl list-timers 'sjc-*'
```

Offline smoke test using the bundled sample sources:

```bash
sudo -u sjcguidance ./deploy/run_monthly.sh --month "April 2026" \
  --sample-data data/sample_april_2026_sources.json --no-llm --no-google
```

## Install For Local Windows Use

From this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

The bundled Codex Python can create the sample DOCX, but live NICE retrieval and Google upload need the packages in `requirements.txt`.

If virtual environment creation is not available on the machine, install dependencies into a local `.deps` folder instead:

```powershell
python -m pip install -r requirements.txt --target .deps
```

`run_monthly.ps1` automatically adds `.deps` to the Python path when it exists.

## Run Monthly Locally On Windows

The PowerShell scripts are for ad-hoc runs from a Windows workstation. The VPS uses the bash runners in `deploy/` instead.

Previous calendar month:

```powershell
.\run_monthly.ps1
```

Specific month:

```powershell
.\run_monthly.ps1 -Month "April 2026"
```

Current calendar month, useful for the last-day monthly automation:

```powershell
.\run_monthly.ps1 -CurrentMonth
```

Skip Google upload:

```powershell
.\run_monthly.ps1 -Month "April 2026" -NoGoogle
```

Offline smoke test using the bundled sample sources:

```powershell
python -m nice_guidance_monitor.cli --config config.json --month "April 2026" --sample-data data\sample_april_2026_sources.json --no-llm --no-google
```

## Run Weekly MHRA Alerts Review

Current 7-day period ending today:

```powershell
.\run_mhra_weekly.ps1
```

Specific week ending date:

```powershell
.\run_mhra_weekly.ps1 -WeekEnding "2026-04-26"
```

Skip Google upload or language-model analysis:

```powershell
.\run_mhra_weekly.ps1 -WeekEnding "2026-04-26" -NoGoogle -NoLlm
```

Live test over a longer window, for example the past 21 days:

```powershell
.\run_mhra_weekly.ps1 -Days 21 -NoGoogle
```

Offline smoke test using the bundled MHRA sample sources:

```powershell
python -m nice_guidance_monitor.mhra_cli --config config.json --week-ending "2026-04-26" --sample-data data\sample_mhra_week_sources.json --no-llm --no-google
```

## Workflow Logic

1. Searches the NICE published guidance listing for guidance and quality standards.
2. Filters items where `Published` or `Last updated` falls inside the target month.
3. De-duplicates by NICE reference number.
4. Opens the actual NICE guidance page and follows same-reference NICE chapter, quality-statement, recommendations, rationale, update information, history, evidence and resource/PDF links where accessible.
5. Extracts key clinical points from every relevant NICE heading/source page, including definitions, recommendation numbers, thresholds, symptom clusters, tables, timeframes, prescribing criteria, monitoring and implementation caveats.
6. Analyses each item for UK primary care relevance, actions, impact and staff groups.
7. Builds the report and source appendix.
8. Creates local Markdown, HTML and DOCX artefacts in the practice house style.
9. Creates the completed report directly as a native Google Doc in the configured Google Drive folder when Google credentials are present.
10. Applies the same house style to the Google Doc, including the banded metadata table, blue section headings and real tables.
11. Sends a completion email alert to the configured notification address with the Google Doc link, reviewed count, included/excluded count and any failures.

## MHRA Weekly Workflow Logic

1. Searches the GOV.UK MHRA alerts, recalls and safety information listing.
2. Reviews items issued in the target 7-day period.
3. Opens each MHRA alert/update page and keeps the source extraction in JSON.
4. Assesses whether there is a realistic GP primary care interface, including prescribing, dispensing-practice stock checks, patient contact, device pathway awareness, care-home implications, or staff briefing.
5. Builds a concise clinical-governance brief with a primary care relevance score and practical GP-setting action.
6. Writes local JSON, Markdown, HTML and DOCX reports, creates a native Google Doc when configured, and sends the completion email where SMTP is configured.

## Error Handling

- If NICE search fails, the run records a retrieval failure and still writes a failure/source report.
- If a linked page or PDF cannot be accessed, the item is marked `source_incomplete`.
- If Google Drive creation is not configured, the Markdown, HTML and DOCX remain in `outputs` and the completion summary says Google Drive was skipped.
- If native Google Doc creation fails, the local artefacts remain available and the completion summary should record the error for manual follow-up.
- If `require_email_notification` is true and SMTP email fails, the run exits non-zero after printing the completion summary, so systemd records the failure.
- If no `OPENAI_API_KEY` is available, the workflow uses a conservative fallback analysis and clearly marks the need for clinician review.
- If a run is already in progress, a second start exits quietly rather than racing it; each job holds an exclusive lock.
- Every VPS run is logged twice: to `logs/` and to the systemd journal for its unit.

## Sample Output

A curated April 2026 sample report is available at:

`outputs/sample/NICE Guidance Monthly Review - April 2026 - Soneh Medical.md`

The smoke-test generated files are written to:

`outputs/April_2026/`

## Clinical Safety Notes

This workflow is for clinical-governance review. It is not a substitute for clinician sign-off. NICE pages and linked documents remain the source of truth; if the source is unclear or inaccessible, the report should state that uncertainty and the item should be checked manually.
