from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .config import load_config, month_bounds
from .nice import NiceClient, load_sample_items
from .analysis import analyse_item, fallback_analysis
from .report import build_markdown_report, build_docx_report
from .google_docs import create_native_google_doc_report
from .notify import send_completion_email


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a monthly NICE guidance governance report.")
    parser.add_argument("--config", default="config.json", help="Path to JSON config.")
    parser.add_argument("--month", help="Target month, for example 'April 2026' or '2026-04'. Defaults to previous calendar month.")
    parser.add_argument("--practice-name", help="Override practice/clinic name.")
    parser.add_argument("--reviewer", help="Override reviewer name/role.")
    parser.add_argument("--sample-data", help="Use a local JSON source list instead of live NICE search.")
    parser.add_argument("--no-google", action="store_true", help="Skip native Google Doc creation even when configured.")
    parser.add_argument("--no-llm", action="store_true", help="Use conservative heuristic analysis only.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    if args.practice_name:
        config["practice_name"] = args.practice_name
    if args.reviewer:
        config["reviewer"] = args.reviewer

    start, end, month_label = month_bounds(args.month, config.get("default_target_month", "previous"))
    out_dir = Path(config.get("output_dir", "outputs")) / month_label.replace(" ", "_")
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.sample_data:
        items = load_sample_items(Path(args.sample_data))
        failures = []
    else:
        client = NiceClient(config["nice"])
        items, failures = client.items_for_month(start, end)

    analysed = []
    for item in items:
        if args.no_llm:
            result = fallback_analysis(item, config)
        else:
            result = analyse_item(item, config)
        analysed.append(result)

    report = {
        "practice_name": config["practice_name"],
        "month_label": month_label,
        "date_generated": date.today().isoformat(),
        "reviewer": config.get("reviewer", ""),
        "items_reviewed": analysed,
        "failures": failures,
        "thresholds": config.get("thresholds", {}),
    }

    title = f"NICE Guidance Monthly Review - {month_label} - {config['practice_name']}"
    json_path = out_dir / f"{title}.json"
    md_path = out_dir / f"{title}.md"
    docx_path = out_dir / f"{title}.docx"

    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(build_markdown_report(report), encoding="utf-8")
    build_docx_report(report, docx_path, config)

    google_doc = None
    if not args.no_google:
        google_doc = create_native_google_doc_report(report, title, config)

    high_actions = [
        action for item in analysed
        for action in item.get("required_actions", [])
        if action.get("priority") in {"high", "urgent"}
    ]

    summary = {
        "title": title,
        "month": month_label,
        "items_reviewed": len(analysed),
        "included": sum(1 for i in analysed if i.get("included")),
        "excluded": sum(1 for i in analysed if not i.get("included")),
        "high_priority_actions": high_actions,
        "markdown": str(md_path),
        "docx": str(docx_path),
        "json": str(json_path),
        "google_doc": google_doc,
        "failures": failures,
    }
    try:
        summary["email_notification_sent_to"] = send_completion_email(summary, config)
    except Exception as exc:
        summary["email_notification_error"] = str(exc)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
