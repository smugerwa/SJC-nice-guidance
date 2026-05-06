from __future__ import annotations

import os
import re
import json
from pathlib import Path


NAVY = {"color": {"rgbColor": {"red": 0.0, "green": 0.125, "blue": 0.376}}}
BLACK = {"color": {"rgbColor": {"red": 0.137, "green": 0.137, "blue": 0.137}}}
PALE_NAVY = {"color": {"rgbColor": {"red": 0.851, "green": 0.886, "blue": 0.953}}}


def create_native_google_doc_report(report: dict, title: str, config: dict) -> dict:
    """Create and format the report directly as a native Google Doc in Drive."""
    folder_id = config.get("destination_drive_folder_id")
    if not folder_id or not _has_google_auth_config(config):
        return {
            "created": False,
            "mode": "skipped",
            "reason": "Google Drive folder ID and Google OAuth or service-account credentials are not configured.",
        }

    drive, docs = _google_services(config)
    created = drive.files().create(
        body={
            "name": title,
            "mimeType": "application/vnd.google-apps.document",
            "parents": [folder_id],
        },
        fields="id,webViewLink",
        supportsAllDrives=True,
    ).execute()

    document_id = created["id"]
    content = _build_native_doc_content(report, title)
    requests = [{"insertText": {"location": {"index": 1}, "text": content["text"]}}]
    requests.extend(_base_text_style_requests(content["text"]))
    requests.extend(content["style_requests"])
    docs.documents().batchUpdate(documentId=document_id, body={"requests": requests}).execute()
    _replace_table_markers(docs, document_id, content["text"], content["tables"])

    return {
        "created": True,
        "id": document_id,
        "url": created.get("webViewLink"),
        "mode": "native_google_doc",
    }


def upload_docx_as_google_doc(docx_path: Path, title: str, config: dict, markdown_path: Path | None = None) -> dict:
    """Legacy fallback: upload a DOCX and convert it to Google Docs."""
    folder_id = config.get("destination_drive_folder_id")
    if not folder_id or not _has_google_auth_config(config):
        return {
            "created": False,
            "mode": "skipped",
            "reason": "Google Drive folder ID and Google OAuth or service-account credentials are not configured.",
        }

    from googleapiclient.http import MediaFileUpload

    drive, docs = _google_services(config)
    metadata = {
        "name": title,
        "mimeType": "application/vnd.google-apps.document",
        "parents": [folder_id],
    }
    media = MediaFileUpload(
        str(docx_path),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        resumable=True,
    )
    try:
        created = drive.files().create(
            body=metadata,
            media_body=media,
            fields="id,webViewLink",
            supportsAllDrives=True,
        ).execute()
        return {"created": True, "id": created["id"], "url": created.get("webViewLink"), "mode": "uploaded_docx"}
    except Exception as exc:
        if not markdown_path or not markdown_path.exists():
            return {"created": False, "mode": "failed", "reason": f"DOCX upload failed: {exc}"}
        fallback = _create_native_summary_doc(
            drive=drive,
            docs=docs,
            folder_id=folder_id,
            title=f"{title} - Summary",
            text=_clean_markdown_for_google_doc(markdown_path.read_text(encoding="utf-8")),
        )
        fallback["warning"] = f"DOCX upload failed; created a native Google Doc summary instead. Error: {exc}"
        return fallback


def _has_google_auth_config(config: dict) -> bool:
    token_path = config.get("google_oauth_token_path")
    return any([
        bool(config.get("google_oauth_client_secret")),
        bool(os.getenv("GOOGLE_OAUTH_TOKEN_JSON")),
        bool(token_path and Path(token_path).exists()),
        bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS")),
    ])


def _google_services(config: dict):
    oauth_client_secret = config.get("google_oauth_client_secret")
    token_path = config.get("google_oauth_token_path")
    if oauth_client_secret or os.getenv("GOOGLE_OAUTH_TOKEN_JSON") or (token_path and Path(token_path).exists()):
        return _google_services_from_user_oauth(config)
    return _google_services_from_service_account()


def _google_services_from_user_oauth(config: dict):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    scopes = ["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/documents"]
    token_path = Path(config.get("google_oauth_token_path") or ".google_token.json")
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)
    elif os.getenv("GOOGLE_OAUTH_TOKEN_JSON"):
        creds = Credentials.from_authorized_user_info(json.loads(os.environ["GOOGLE_OAUTH_TOKEN_JSON"]), scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not config.get("google_oauth_client_secret"):
                raise RuntimeError(
                    "Google OAuth token is missing or invalid, and google_oauth_client_secret is not configured "
                    "for an interactive re-authorisation."
                )
            print(
                "Opening Google authorisation. If Google shows 'Access blocked', add the signed-in account "
                "as a test user in Google Cloud Console > APIs & Services > OAuth consent screen > Audience.",
                flush=True,
            )
            flow = InstalledAppFlow.from_client_secrets_file(config["google_oauth_client_secret"], scopes)
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return build("drive", "v3", credentials=creds), build("docs", "v1", credentials=creds)


def _google_services_from_service_account():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    scopes = ["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/documents"]
    creds = service_account.Credentials.from_service_account_file(
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
        scopes=scopes,
    )
    return build("drive", "v3", credentials=creds), build("docs", "v1", credentials=creds)


def _build_native_doc_content(report: dict, title: str) -> dict:
    source_label = report.get("source_label", "NICE")
    report_title = report.get("report_title", f"{source_label} Guidance Monthly Review")
    period_label = report.get("period_label", "Reporting month")
    prepared_by = report.get("prepared_by", f"{source_label} Guidance Monitoring Agent")
    included = [i for i in report["items_reviewed"] if i.get("included")]
    excluded = [i for i in report["items_reviewed"] if not i.get("included")]
    included = sorted(included, key=lambda item: item.get("relevance", {}).get("score", 0), reverse=True)
    high_min = report.get("thresholds", {}).get("high_relevance_min_score", 4)
    clinically_relevant = [i for i in included if i.get("relevance", {}).get("score", 0) >= 3]
    high = [i for i in clinically_relevant if i.get("relevance", {}).get("score", 0) >= high_min]
    low_relevance = [i for i in included if i.get("relevance", {}).get("score", 0) < 3]

    lines: list[str] = []
    heading_lines: set[str] = set()
    item_heading_lines: set[str] = set()
    label_lines: set[str] = set()
    tables: list[dict] = []

    def add(line: object = "", kind: str | None = None) -> None:
        cleaned = _clean_doc_text(line)
        lines.append(cleaned)
        if kind == "heading":
            heading_lines.add(cleaned)
        elif kind == "item":
            item_heading_lines.add(cleaned)
        elif kind == "label":
            label_lines.add(cleaned)

    def add_table(marker: str, rows: list[list[object]]) -> None:
        add(marker)
        tables.append({"marker": marker, "rows": [[_clean_doc_text(cell) for cell in row] for row in rows]})

    add(report["practice_name"], "item")
    add(report_title, "heading")
    add(f"{period_label}: {report['month_label']}")
    add()
    add(title, "heading")
    add(f"Date generated: {report['date_generated']}")
    add(f"Prepared by: {prepared_by}")
    add(f"Reviewed by: {report.get('reviewer') or '[INSERT NAME/ROLE]'}")
    add("Clinical governance document - for internal use")
    add()

    add("Executive Summary", "heading")
    add(f"{source_label} items reviewed: {len(report['items_reviewed'])}")
    add(f"Included in clinical brief: {len(clinically_relevant)}")
    add(f"Excluded or appendix only: {len(excluded)}")
    add(f"High or very high primary care relevance: {len(high)}")
    add()

    add("Key Points For Clinical Meeting", "heading")
    if clinically_relevant:
        for item in clinically_relevant[:6]:
            ident = item["guidance_identification"]
            brief = item.get("clinical_brief", {})
            add(f"- {_item_reference(ident)} - {ident.get('title')}: {brief.get('what_changed', '').strip()}")
    else:
        add("- No clinically relevant updates identified for routine primary care.")
    add()

    add("Action Dashboard", "heading")
    action_rows = [[f"{source_label} item", "Score", "What to do", "Meeting question"]]
    for item in clinically_relevant:
        ident = item["guidance_identification"]
        brief = item.get("clinical_brief", {})
        action_rows.append([
            f"{_item_reference(ident)} - {ident.get('title')}",
            str(item.get("relevance", {}).get("score", "")),
            brief.get("suggested_action", ""),
            brief.get("meeting_discussion", ""),
        ])
    add_table("[[TABLE_ACTION_DASHBOARD]]", action_rows)
    add()

    add("Clinical Update Briefs", "heading")
    for item in clinically_relevant:
        ident = item["guidance_identification"]
        brief = item.get("clinical_brief", {})
        add()
        add(f"{_item_reference(ident)} - {ident.get('title')}", "item")
        add(f"Type: {ident.get('guidance_type', '')}", "label")
        add(f"Date: {ident.get('publication_or_update_date', '')}", "label")
        add(f"Status: {ident.get('status', '')}", "label")
        add(
            "Primary care relevance: "
            f"{item.get('relevance', {}).get('score', '')}/5 - {item.get('relevance', {}).get('rationale', '')}",
            "label",
        )
        add(f"{source_label} source: {ident.get('url', '')}", "label")
        add("What Changed Or Matters", "item")
        add(brief.get("what_changed", ""))
        add("Key Takeaways For Clinicians", "item")
        for point in brief.get("key_takeaways") or item.get("key_clinical_points", [])[:5]:
            add(f"- {point}")
        add("Practice Implication", "item")
        add(brief.get("practice_implication", ""))
        add("Suggested Meeting Discussion", "item")
        add(f"- {brief.get('meeting_discussion', '')}")
        add("Suggested Action", "item")
        add(f"- {brief.get('suggested_action', '')}")

    add()
    add("Items For Clinical Meeting", "heading")
    meeting_rows = [["Type", "Item", "Meeting prompt"]]
    for item in clinically_relevant:
        ident = item["guidance_identification"]
        score = item.get("relevance", {}).get("score", 0)
        category = "Decision" if score >= high_min else "Discussion"
        meeting_rows.append([
            category,
            f"{_item_reference(ident)} - {ident.get('title')}",
            item.get("clinical_brief", {}).get("meeting_discussion", ""),
        ])
    add_table("[[TABLE_MEETING_ITEMS]]", meeting_rows)
    add()

    add(f"Appendix A: Low-Relevance Or Excluded {source_label} Items", "heading")
    appendix_rows = [["Reference", "Title", "Reason"]]
    for item in excluded:
        ident = item["guidance_identification"]
        appendix_rows.append([_item_reference(ident), ident.get("title", ""), item.get("exclusion_reason", "")])
    for item in low_relevance:
        ident = item["guidance_identification"]
        appendix_rows.append([_item_reference(ident), ident.get("title", ""), "Low primary care relevance; awareness only."])
    if len(appendix_rows) == 1:
        appendix_rows.append(["None", "", ""])
    add_table("[[TABLE_APPENDIX_A]]", appendix_rows)
    add()

    add(f"Appendix B: Main {source_label} Sources", "heading")
    source_rows = [["Reference", "Guidance", "URL"]]
    for item in report["items_reviewed"]:
        ident = item.get("guidance_identification", {})
        if ident.get("url"):
            source_rows.append([_item_reference(ident), ident.get("title", ""), ident.get("url", "")])
    add_table("[[TABLE_SOURCES]]", source_rows)
    add()
    add("Full linked-source extraction is retained in the JSON source log for audit, but omitted from this meeting brief for readability.")

    text = "\n".join(lines).strip() + "\n"
    return {
        "text": text,
        "tables": tables,
        "style_requests": _native_content_style_requests(text, heading_lines, item_heading_lines, label_lines),
    }


def _item_reference(ident: dict) -> str:
    return ident.get("source_reference") or ident.get("nice_reference") or ident.get("reference") or "MHRA"


def _native_content_style_requests(
    text: str,
    heading_lines: set[str],
    item_heading_lines: set[str],
    label_lines: set[str],
) -> list[dict]:
    requests: list[dict] = []
    cursor = 1
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\n")
        start = cursor
        end = cursor + len(line)
        cursor += len(raw_line)
        if not line.strip():
            continue
        if line in heading_lines:
            requests.append(_text_style_request(
                start,
                end,
                {"bold": True, "foregroundColor": NAVY, "fontSize": {"magnitude": 15, "unit": "PT"}},
                "bold,foregroundColor,fontSize",
            ))
        elif line in item_heading_lines:
            requests.append(_text_style_request(start, end, {"bold": True, "foregroundColor": NAVY}, "bold,foregroundColor"))
        elif line in label_lines:
            label_end = start + len(line.split(":", 1)[0]) + 1
            requests.append(_text_style_request(start, min(label_end, end), {"bold": True, "foregroundColor": NAVY}, "bold,foregroundColor"))
    return requests


def _replace_table_markers(docs, document_id: str, text: str, tables: list[dict]) -> None:
    for table in sorted(tables, key=lambda item: text.find(item["marker"]), reverse=True):
        marker = table["marker"]
        marker_index = text.find(marker)
        if marker_index < 0:
            continue
        start = marker_index + 1
        rows = table["rows"]
        docs.documents().batchUpdate(
            documentId=document_id,
            body={
                "requests": [
                    {"deleteContentRange": {"range": {"startIndex": start, "endIndex": start + len(marker)}}},
                    {"insertTable": {"location": {"index": start}, "rows": len(rows), "columns": len(rows[0])}},
                ]
            },
        ).execute()
        document = docs.documents().get(documentId=document_id).execute()
        table_element = _find_table_element(document, start)
        if table_element:
            _fill_google_table(docs, document_id, table_element, rows)


def _find_table_element(document: dict, target_index: int) -> dict | None:
    tables = [element for element in document.get("body", {}).get("content", []) if "table" in element]
    if not tables:
        return None
    return min(tables, key=lambda element: abs(element.get("startIndex", 0) - target_index))


def _fill_google_table(docs, document_id: str, table_element: dict, rows: list[list[str]]) -> None:
    insert_requests = []
    table = table_element["table"]
    for row_index, row in enumerate(rows):
        for col_index, value in enumerate(row):
            try:
                cell = table["tableRows"][row_index]["tableCells"][col_index]
                cell_index = cell["content"][0]["startIndex"]
            except (KeyError, IndexError):
                continue
            if value:
                insert_requests.append({"index": cell_index, "text": value})

    if insert_requests:
        docs.documents().batchUpdate(
            documentId=document_id,
            body={
                "requests": [
                    {"insertText": {"location": {"index": item["index"]}, "text": item["text"]}}
                    for item in sorted(insert_requests, key=lambda item: item["index"], reverse=True)
                ]
            },
        ).execute()

    document = docs.documents().get(documentId=document_id).execute()
    table_element = _find_table_element(document, table_element.get("startIndex", 0))
    if not table_element:
        return

    table_start = table_element["startIndex"]
    table_end = table_element["endIndex"]
    style_requests = [
        _text_style_request(
            table_start,
            table_end,
            {
                "weightedFontFamily": {"fontFamily": "Calibri"},
                "fontSize": {"magnitude": 10, "unit": "PT"},
                "foregroundColor": BLACK,
            },
            "weightedFontFamily,fontSize,foregroundColor",
        ),
        {
            "updateTableCellStyle": {
                "tableRange": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": table_start},
                        "rowIndex": 0,
                        "columnIndex": 0,
                    },
                    "rowSpan": 1,
                    "columnSpan": len(rows[0]),
                },
                "tableCellStyle": {"backgroundColor": PALE_NAVY},
                "fields": "backgroundColor",
            }
        },
    ]

    for cell in table_element["table"]["tableRows"][0]["tableCells"]:
        start = cell["content"][0]["startIndex"]
        end = max(start + 1, cell["content"][-1]["endIndex"] - 1)
        style_requests.append(_text_style_request(start, end, {"bold": True, "foregroundColor": NAVY}, "bold,foregroundColor"))

    docs.documents().batchUpdate(documentId=document_id, body={"requests": style_requests}).execute()


def _create_native_summary_doc(drive, docs, folder_id: str, title: str, text: str) -> dict:
    created = drive.files().create(
        body={
            "name": title,
            "mimeType": "application/vnd.google-apps.document",
            "parents": [folder_id],
        },
        fields="id,webViewLink",
        supportsAllDrives=True,
    ).execute()
    if text:
        requests = [{"insertText": {"location": {"index": 1}, "text": text}}]
        requests.extend(_base_text_style_requests(text))
        docs.documents().batchUpdate(documentId=created["id"], body={"requests": requests}).execute()
    return {"created": True, "id": created["id"], "url": created.get("webViewLink"), "mode": "native_summary_fallback"}


def _base_text_style_requests(text: str) -> list[dict]:
    requests: list[dict] = [
        _text_style_request(
            1,
            len(text) + 1,
            {
                "weightedFontFamily": {"fontFamily": "Calibri"},
                "fontSize": {"magnitude": 12, "unit": "PT"},
                "foregroundColor": BLACK,
            },
            "weightedFontFamily,fontSize,foregroundColor",
        )
    ]
    cursor = 1
    major_headings = {
        "Executive Summary",
        "Key Points For Clinical Meeting",
        "Action Dashboard",
        "Clinical Update Briefs",
        "Items For Clinical Meeting",
        "Appendix A: Low-Relevance Or Excluded NICE Items",
        "Appendix B: Main NICE Sources",
        "Appendix A: Low-Relevance Or Excluded MHRA Items",
        "Appendix B: Main MHRA Sources",
    }
    section_labels = {
        "What Changed Or Matters",
        "Key Takeaways For Clinicians",
        "Practice Implication",
        "Suggested Meeting Discussion",
        "Suggested Action",
        "Source",
    }
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\n")
        start = cursor
        end = cursor + len(line)
        cursor += len(raw_line)
        if not line.strip():
            continue
        if start == 1 or line in major_headings:
            requests.append(_text_style_request(
                start,
                end,
                {"bold": True, "foregroundColor": NAVY, "fontSize": {"magnitude": 15, "unit": "PT"}},
                "bold,foregroundColor,fontSize",
            ))
        elif re.match(r"^((NG|CG|QS|TA|HTG|DG|IPG|MTG)\d+|EL\(\d{2}\)A/\d+|NatPSA/\d{4}/\d+/[A-Z]+|DSI/\d{4}/\d+|MHRA)\s+-\s+", line):
            requests.append(_text_style_request(start, end, {"bold": True, "foregroundColor": NAVY}, "bold,foregroundColor"))
        elif any(line.startswith(label + ":") or line == label for label in section_labels):
            requests.append(_text_style_request(start, end, {"bold": True, "foregroundColor": NAVY}, "bold,foregroundColor"))
    return requests


def _text_style_request(start: int, end: int, style: dict, fields: str) -> dict:
    return {
        "updateTextStyle": {
            "range": {"startIndex": start, "endIndex": max(start + 1, end)},
            "textStyle": style,
            "fields": fields,
        }
    }


def _clean_markdown_for_google_doc(markdown: str) -> str:
    text = markdown.replace("\r\n", "\n")
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    text = text.replace("**", "")
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if re.fullmatch(r"\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*", line):
            continue
        if line.lstrip().startswith("|") and line.rstrip().endswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            lines.append("\t".join(cells))
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^_\s*(.*?)\s*_$", r"\1", line)
        lines.append(line)
    return "\n".join(lines).strip() + "\n"


def _clean_doc_text(text: object) -> str:
    if text is None:
        return ""
    value = str(text).replace("**", "").strip()
    replacements = {
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2022": "-",
        "Ã‚": "",
    }
    for bad, good in replacements.items():
        value = value.replace(bad, good)
    return value
