from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def send_completion_email(summary: dict, config: dict) -> str | None:
    recipient = config.get("email_notification")
    smtp_config = config.get("smtp", {})
    host = smtp_config.get("host")
    sender = smtp_config.get("from_address")
    if not recipient or not host or not sender:
        return None
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    if smtp_config.get("require_auth", True) and (not username or not password):
        return None

    monitor_label = summary.get("monitor_label", "NICE guidance review")
    message = EmailMessage()
    message["Subject"] = f"{monitor_label} complete - {summary['month']}"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        "\n".join([
            f"Report: {summary['title']}",
            f"Items reviewed: {summary['items_reviewed']}",
            f"Included: {summary['included']}",
            f"Excluded: {summary['excluded']}",
            f"Markdown: {summary['markdown']}",
            f"DOCX: {summary['docx']}",
            f"Google Doc: {summary.get('google_doc') or 'Not created'}",
            "",
            "High-priority actions:",
            *[f"- {action.get('priority')}: {action.get('classification')} - {action.get('reason')}" for action in summary.get("high_priority_actions", [])],
            "",
            "Failures:",
            *[f"- {failure}" for failure in summary.get("failures", [])],
        ])
    )

    port = int(smtp_config.get("port", 587))
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        if smtp_config.get("use_tls", True):
            smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.send_message(message)
    return recipient
