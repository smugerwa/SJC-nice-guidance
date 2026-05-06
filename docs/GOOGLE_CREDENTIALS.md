# Google Credentials Setup

The workflow creates the completed NICE monthly report directly as a native Google Doc in the configured Drive folder. It uses the structured report data to apply Calibri 12 body text, navy headings, bold section labels and real Google Docs tables.

The preferred authentication route is user OAuth, because it creates the Google Doc as your Google Drive user and avoids service-account storage-quota problems.

## One-Time Google Cloud Setup

1. Go to Google Cloud Console.
2. Create or choose a project.
3. Enable these APIs:
   - Google Drive API
   - Google Docs API
4. Create an OAuth client for a desktop app and download the client-secret JSON.
5. Save the JSON somewhere outside the repo, for example:

```powershell
C:\Users\soul.mugerwa\Downloads\client_secret_xxx.apps.googleusercontent.com.json
```

## Configure The Workflow

`config.json` should contain:

```json
"google_oauth_client_secret": "C:\\Users\\soul.mugerwa\\Downloads\\client_secret_xxx.apps.googleusercontent.com.json",
"google_oauth_token_path": ".google_token.json",
"destination_drive_folder_id": "1QV_T89-7gxx0UvmGKuT2eVFmeZypxT9t"
```

The first run opens a Google sign-in/consent page. After approval, the workflow saves `.google_token.json` for future monthly runs.

## If Google Says Access Blocked

If the browser says:

```text
Access blocked: Codex has not completed the Google verification process
Error 403: access_denied
```

the OAuth app is still in testing mode and your signed-in Google account has not been added as a test user.

Fix:

1. Open Google Cloud Console.
2. Select project `gen-lang-client-0147915531`.
3. Go to **APIs & Services**.
4. Open **OAuth consent screen**.
5. Open **Audience**.
6. Under **Test users**, add the Google account you are signing in with, for example:

```text
info@skinjointclinic.co.uk
```

7. Save the change.
8. Run the test again:

```powershell
.\run_monthly.ps1 -Month "April 2026"
```

This follows Google's testing-mode rule: apps in testing can only be authorised by accounts listed as test users.

## Optional Service Account Route

Service accounts can read a folder shared with them, but may fail when creating files in a normal My Drive folder because of Drive storage quota. Use OAuth unless the destination is a suitable Shared Drive or your Google Workspace admin has configured domain-wide delegation.

Leave `google_doc_template_id` blank. The recommended path is direct native Google Doc creation in the destination folder; the local DOCX remains a fallback/reference artefact.

## Test Google Doc Creation

Run:

```powershell
.\run_monthly.ps1 -Month "April 2026"
```

If OAuth is configured and `.google_token.json` exists, the completion summary should include a Google Doc URL.
