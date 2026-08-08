# NICE Guidance Monthly Review Automation

This workflow creates a monthly clinical-governance report for NICE guidance that was published or updated in a target month. It is designed for a UK general practice or private primary care clinic and uses NICE guidance pages as the source of truth.

## What It Produces

- A structured source log as JSON.
- A Markdown report for easy review or fallback use.
- A headed-paper DOCX using the configured clinic template where available.
- A native Google Doc created directly in the configured Google Drive folder when Google credentials are available.
- The native Google Doc is generated from the structured report data, not from a DOCX upload, and applies Calibri 12 body text, navy headings and real Google Docs tables for dashboards and appendices.

## Files To Edit

Edit `config.json`:

- `practice_name`: clinic or practice name.
- `letterhead_name`: name shown in the page header of every report, e.g. `Soneh Medical Ltd`.
- `reviewer`: named reviewer or role.
- `profiles`: optional list of practice profiles. Sources are retrieved once per run, then each profile gets its own relevance analysis, report set, output folder (`outputs/<id>/...`), destination and email. Each profile can override any top-level key and adds: `audience` (`primary_care` for the standard GP-practice logic, `custom` to score against the profile's own services), `scope_description` / `scope_inclusion_rule` (text driving the AI relevance assessment for `custom` audiences), `scope_keywords` (offline fallback heuristics), and `storage` (`gdrive`, or `pending_sharepoint` to keep files local until a SharePoint destination is configured). With no `profiles` key the behaviour is unchanged: one report from the top-level values.
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

The scheduled Codex automation also sends an Outlook alert to `email_notification` after each successful run, using the Google Doc link from the workflow summary. SMTP is optional and can remain blank if the Outlook connector route is used.

Google Drive setup is documented in `docs/GOOGLE_CREDENTIALS.md`.

GitHub Actions/cloud setup is documented in `docs/GITHUB_CLOUD.md`.

## Install

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

## Run Monthly

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

> **Retired for Soneh Medical, 8 August 2026 — not scheduled any more.**
>
> The VPS cron line that ran this every Monday at 08:30 has been removed. Soneh
> Medical's MHRA review now happens in the Soneh Hub
> (`hub.skinjointclinic.co.uk/compliance/mhra`): the clinician reviews each alert
> as it arrives and saving it generates a per-alert review document in the same
> Drive folder, with the summary, relevance, justification and Actions Completed
> table. That replaced a weekly document produced on a timer whether or not
> anything had been reviewed.
>
> **Do not re-add the cron line** — it would refill the Drive folder with
> untriggered weekly documents alongside the per-alert ones. The commands below
> still work for a one-off backfill or for the Church Road profile, which is
> unaffected. The monthly NICE run (1st, 07:30) is also unaffected.

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
8. Creates local Markdown and DOCX fallback artefacts.
9. Creates the completed report directly as a native Google Doc in the configured Google Drive folder when Google credentials are present.
10. Applies Google Docs formatting directly, including Calibri 12 body text, navy headings, bold section labels and real tables.
11. Sends a completion email alert to the configured notification address with the Google Doc link, reviewed count, included/excluded count and any failures.

## MHRA Weekly Workflow Logic

1. Searches the GOV.UK MHRA alerts, recalls and safety information listing.
2. Reviews items issued in the target 7-day period.
3. Opens each MHRA alert/update page and keeps the source extraction in JSON.
4. Assesses whether there is a realistic GP primary care interface, including prescribing, dispensing-practice stock checks, patient contact, device pathway awareness, care-home implications, or staff briefing.
5. Builds a concise clinical-governance brief with a primary care relevance score and practical GP-setting action.
6. Writes local JSON, Markdown and DOCX reports, creates a native Google Doc when configured, and sends the completion email where SMTP is configured.

## Error Handling

- If NICE search fails, the run records a retrieval failure and still writes a failure/source report.
- If a linked page or PDF cannot be accessed, the item is marked `source_incomplete`.
- If Google Drive creation is not configured, the Markdown and DOCX remain in `outputs` and the completion summary says Google Drive was skipped.
- If native Google Doc creation fails, the Markdown and DOCX remain available locally and the completion summary should record the error for manual follow-up.
- If `require_email_notification` is true and SMTP email fails, the cloud run fails visibly after printing the completion summary.
- If no `OPENAI_API_KEY` is available, the workflow uses a conservative fallback analysis and clearly marks the need for clinician review.

## Sample Output

A curated April 2026 sample report is available at:

`outputs/sample/NICE Guidance Monthly Review - April 2026 - Soneh Medical.md`

The smoke-test generated files are written to:

`outputs/April_2026/`

## Clinical Safety Notes

This workflow is for clinical-governance review. It is not a substitute for clinician sign-off. NICE pages and linked documents remain the source of truth; if the source is unclear or inaccessible, the report should state that uncertainty and the item should be checked manually.
