---
name: nice-guidance-monitor
description: Create concise clinician-facing monthly NICE guidance review reports for UK primary care and private GP clinics. Use when asked to monitor NICE guidance, summarise monthly NICE updates, prepare clinical governance meeting briefs, extract primary-care practice changes, or run/update the NICE guidance automation.
metadata:
  short-description: Monthly NICE clinical governance brief
---

# NICE Guidance Monitor

Use this skill for monthly NICE guidance monitoring for UK NHS general practice or private primary care clinics.

## Desired Output

The visible report must be a clean **clinical meeting brief**, not a source dump.

For each included NICE item, provide:

1. **What changed or matters**
   - One concise paragraph.
   - If the monthly update is administrative only, say so clearly.
   - If the standing guidance remains clinically useful, summarise the current key practice points.

2. **Key takeaways for clinicians**
   - 3 to 6 bullets.
   - Include exact clinical details that affect practice: first-line treatments, thresholds, timeframes, referral triggers, prescribing restrictions, monitoring, safety-netting, governance caveats.
   - Use brand examples only as explanatory context, and qualify with local formulary approval where relevant.

3. **Practice implication**
   - One practical statement about whether to update a template, SOP, formulary, pathway, patient information, audit, or staff briefing.

4. **Suggested meeting discussion**
   - One ready-to-paste question for the clinical/governance meeting.

5. **Suggested action**
   - One practical owner/action line.

Keep detailed source extraction in JSON or an audit log, not in the readable report.

## DOCX Presentation Standard

The DOCX report should look like a polished clinical governance document, not exported Markdown.

Use:

- Main body font: Calibri, 12 pt.
- Heading font: Calibri.
- Heading colour/accent: navy blue, preferably `#002060`.
- Heading hierarchy: large clear H1 headings, smaller H2/H3 headings, all bold where appropriate.
- Tables for action dashboards, meeting items, appendices and source lists.
- Clean table header shading in a pale navy tint.
- Real Word bold text and real Word headings, not Markdown markers.
- No visible asterisks, pipe-table text, raw Markdown syntax, or unformatted URLs embedded in body paragraphs where a table is more suitable.

Before handoff, structurally verify:

- body text is Calibri 12,
- headings are navy,
- tables are real Word tables,
- visible text contains no `**` Markdown artefacts,
- the report remains concise and easy to scan.

## Inclusion Rules

Include items with a realistic UK primary care interface:

- common GP presentations
- prescribing, formulary or monitoring changes
- referral criteria/pathway changes
- cancer recognition/safety-netting
- diagnostics used in primary care/community settings
- patient-facing or care-navigation implications
- governance/audit standards relevant to GP practice

Move to appendix:

- specialist tertiary-only drugs or procedures with no routine GP action
- specialist-only technology appraisals where the only action is an NHS England/commissioner funding mandate
- oncology drugs, advanced cancer therapies, tertiary procedures or hospital-only treatments unless there is a concrete GP prescribing, monitoring, referral, diagnostic, safety-netting, patient-advice or shared-care action
- terminated appraisals
- duplicate/legacy guidance where the action is already captured under a newer item
- administrative-only updates unless the standing guidance is highly relevant to primary care

Do not include an item in the main clinical meeting brief merely because clinicians may need "awareness". Awareness-only specialist items belong in Appendix A. The visible report should contain only items that help a GP practice decide what to change, discuss, audit, brief, prescribe, monitor, refer, code, safety-net, or communicate to patients.

## Writing Standard

Write for clinicians who need to scan the report before a meeting.

- Prefer "what do we need to do?" over long explanation.
- Do not paste NICE text at length.
- Do not include every source URL in the visible report; list main NICE pages only.
- Keep wording cautious and clinically accurate.
- State uncertainty when an update appears administrative or source detail is unclear.
- The report is for governance review and clinician sign-off, not patient-specific advice.

## Automation Workflow

In this workspace, the runnable workflow is:

```powershell
.\run_monthly.ps1 -CurrentMonth
```

For a manual test month:

```powershell
.\run_monthly.ps1 -Month "April 2026" -NoGoogle
```

The workflow should:

1. Search NICE published guidance and quality-standard listings for the target month.
2. Retrieve the actual guidance page and linked NICE chapter/resource/PDF pages.
3. Keep detailed source extraction in the JSON source log.
4. Generate a concise clinical update report in Markdown and DOCX as local fallback artefacts.
5. Create the completed report directly as a native Google Doc in the configured Google Drive folder when Google credentials and Drive config are available.
6. Send a completion email alert to the configured notification address.
7. Return a completion summary including document paths/link, reviewed count, included/excluded count, email status and failures.

## Google Drive Output

The completed monthly summary should be created directly as a native Google Doc in Google Drive whenever possible.

Preferred output:

- Create a new native Google Doc in the configured Google Drive destination folder.
- Build the report from the structured analysis data, not from Markdown paste or DOCX upload.
- Apply Google Docs formatting directly: Calibri 12 body text, navy headings, bold section labels and real Google Docs tables for the action dashboard, meeting items, appendices and source list.
- Return the Google Doc link in the completion summary.

Credential requirements:

- `destination_drive_folder_id` must be set in `config.json`.
- Preferred: `google_oauth_client_secret` should point to a desktop OAuth client JSON file, with `google_oauth_token_path` set to `.google_token.json`.
- The first OAuth run opens a Google sign-in page and saves `.google_token.json` for future monthly runs.
- If Google shows `Access blocked` / `Error 403: access_denied`, add the signed-in Google account as a test user in Google Cloud Console > APIs & Services > OAuth consent screen > Audience.
- Service-account credentials are a fallback only; they can read shared folders but may fail to create files in a normal My Drive folder because of Drive quota.

Fallback behaviour:

- If credentials are missing or OAuth is blocked, do not pretend Drive output succeeded; state that Google Drive creation was skipped and keep the local DOCX/Markdown.
- If native Google Doc creation fails, keep the local DOCX/Markdown and record the error for manual follow-up.
- If working through the connected Google Drive plugin during an interactive Codex session, be clear if the exposed connector tools cannot create inside the target folder; the saved OAuth token workflow is the production route for folder placement.

## Current Local Configuration

The project is in:

`C:\Users\soul.mugerwa\Documents\New project 3`

The Drive destination folder configured in `config.json` is:

`1QV_T89-7gxx0UvmGKuT2eVFmeZypxT9t`

The headed paper DOCX configured in `config.json` is:

`C:\Users\soul.mugerwa\Downloads\Soneh Medical Document Template.docx`

The email notification recipient configured in `config.json` is:

`info@skinjointclinic.co.uk`

## Email Notification

Every scheduled run should send a short completion alert to `info@skinjointclinic.co.uk`.

Use the Outlook connector from the automation agent when SMTP is not configured. The email should include:

- report title and month,
- Google Doc link,
- number of NICE items reviewed,
- included and excluded counts,
- high-priority actions, if any,
- failures or inaccessible sources, if any.

If the local workflow already sent an SMTP email, do not send a duplicate Outlook email. If no email could be sent, state this clearly in the completion summary.

## Good Example

For NICE acne guidance, do not write “review acne guidance”.

Write a clinician-facing brief like:

- Offer a 12-week first-line course based on severity and preference.
- Fixed topical adapalene + benzoyl peroxide is a NICE first-line option for any acne severity, corresponding to products such as Epiduo where locally formulary-approved.
- For moderate to severe acne, combine topical therapy with oral lymecycline or doxycycline where appropriate.
- Review at 12 weeks.
- Avoid prolonged antibiotic-containing regimens; continue beyond 6 months only exceptionally with 3-monthly review.

Practice implication: check acne template/formulary advice and antibiotic stewardship wording.

Meeting question: do our acne prescribing templates reflect NICE first-line fixed-combination options, 12-week review, and antibiotic stewardship?
