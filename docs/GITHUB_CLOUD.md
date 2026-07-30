# GitHub Cloud Run Setup (manual fallback)

The monthly schedule lives on the Hostinger VPS, in the `sjc-nice-monthly.timer` systemd timer. See `docs/VPS_HOSTINGER.md` for the primary setup.

This workflow is kept as a manual fallback for when the VPS is unavailable. It has no schedule, so it cannot double-run against the VPS timer and produce two reports for the same month. Triggered by hand it runs the same code and creates the NICE review directly as a native Google Doc.

## Required Repository Secrets

Add these in GitHub:

`Settings > Secrets and variables > Actions > New repository secret`

Required:

- `OPENAI_API_KEY`: OpenAI API key for the clinical analysis.
- `GOOGLE_OAUTH_TOKEN_JSON`: the full contents of the local `.google_token.json` file.

Optional, for email alerts from GitHub Actions:

- `SMTP_USERNAME`: mailbox username, usually `info@skinjointclinic.co.uk`.
- `SMTP_PASSWORD`: mailbox password or app password for SMTP.

The workflow is already configured to send alerts to:

```text
info@skinjointclinic.co.uk
```

using:

```text
smtp.office365.com:587
```

## Email Troubleshooting

The cloud test confirmed that Google Doc creation works. If the run fails at the email step with:

```text
535 5.7.139 Authentication unsuccessful
```

Microsoft 365 has rejected SMTP authentication. Common fixes:

- Use `SMTP_USERNAME=info@skinjointclinic.co.uk`.
- Use an app password if the mailbox/account uses multi-factor authentication and app passwords are allowed.
- In Microsoft 365 admin, enable **Authenticated SMTP** for the mailbox.
- Check tenant security defaults or conditional access rules; these can block SMTP AUTH entirely.

Because the email alert is required, `config.cloud.json` sets:

```json
"require_email_notification": true
```

This means runs fail visibly if the report is created but the email alert cannot be sent. The same applies on the VPS through `config.vps.json`.

## Schedule

There is no GitHub schedule. The last-day-of-month run is a systemd timer on the VPS, where `OnCalendar=*-*~01` expresses "last day of the month" directly.

Manual runs are available from:

`Actions > NICE Guidance Monthly Review > Run workflow`

You can optionally provide a month such as:

```text
April 2026
```

## Files Used In Cloud

- `.github/workflows/nice-guidance-monthly.yml`: GitHub Actions workflow.
- `config.cloud.json`: cloud-safe config.
- `.google_token.json`: not committed; supplied through the `GOOGLE_OAUTH_TOKEN_JSON` repository secret.
- `outputs/`: not committed; uploaded as a workflow artifact after each run.

## Important Safety Note

Do not commit:

- `.google_token.json`
- `config.json`
- local credential files
- generated reports in `outputs/`

These are ignored by `.gitignore`.
