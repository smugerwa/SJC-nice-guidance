# GitHub Cloud Run Setup

This project can run monthly in GitHub Actions and create the NICE review directly as a native Google Doc.

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

This means future cloud runs fail visibly if the report is created but the email alert cannot be sent.

## Schedule

GitHub Actions cannot express "last day of month" directly in cron. The workflow wakes up at 17:00 on days 28 to 31 and runs only when tomorrow is the first day of a new month.

Manual runs are also available from:

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
