from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .config import load_config, week_bounds, get_profiles
from .google_docs import create_native_google_doc_report
from .mhra import MhraClient, load_sample_items
from .mhra_analysis import analyse_item, fallback_analysis
from .notify import send_completion_email
from .report import build_docx_report, build_markdown_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a weekly MHRA alerts and updates governance report.")
    parser.add_argument("--config", default="config.json", help="Path to JSON config.")
    parser.add_argument("--week-ending", help="Week ending date as YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--days", type=int, default=7, help="Number of days to review ending on --week-ending. Defaults to 7.")
    parser.add_argument("--practice-name", help="Override practice/clinic name.")
    parser.add_argument("--reviewer", help="Override reviewer name/role.")
    parser.add_argument("--sample-data", help="Use a local JSON source list instead of live MHRA search.")
    parser.add_argument("--no-google", action="store_true", help="Skip native Google Doc creation even when configured.")
    parser.add_argument("--no-llm", action="store_true", help="Use conservative heuristic analysis only.")
    parser.add_argument("--profile", help="Run only the profile with this id (e.g. soneh-medical).")
    parser.add_argument("--no-email", action="store_true", help="Skip the completion email (e.g. for backfill runs).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    if args.practice_name:
        config["practice_name"] = args.practice_name
    if args.reviewer:
        config["reviewer"] = args.reviewer

    start, end, period_label = week_bounds(args.week_ending, args.days)

    if args.sample_data:
        items = load_sample_items(Path(args.sample_data))
        failures = []
    else:
        client = MhraClient(config.get("mhra", {}))
        items, failures = client.items_for_period(start, end)

    # Sources are retrieved once; each practice profile then gets its own
    # relevance analysis, report set and destination.
    profiles = get_profiles(config)
    if args.profile:
        profiles = [p for p in profiles if p.get("profile_id") == args.profile]
        if not profiles:
            raise SystemExit(f"No profile with id '{args.profile}' in the config.")
    summaries = []
    for profile in profiles:
        summaries.append(_run_profile(profile, items, list(failures), period_label, end, args))

    print(json.dumps(summaries if len(summaries) > 1 else summaries[0], indent=2))
    failed_emails = [s["title"] for s in summaries if s.get("email_notification_error")]
    if config.get("require_email_notification") and failed_emails:
        raise SystemExit(f"Email notification failed for: {', '.join(failed_emails)}; see completion summary above.")


def _run_profile(profile: dict, items: list, failures: list, period_label: str, end, args) -> dict:
    period_dir = "Week_ending" if args.days == 7 else f"{args.days}_days_ending"
    out_dir = Path(profile.get("output_dir", "outputs"))
    if profile.get("profile_id"):
        out_dir = out_dir / profile["profile_id"]
    out_dir = out_dir / "MHRA" / f"{period_dir}_{end.isoformat()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    analysed = []
    for item in items:
        if args.no_llm:
            result = fallback_analysis(item, profile)
        else:
            result = analyse_item(item, profile)
        analysed.append(result)

    report = {
        "practice_name": profile["practice_name"],
        "month_label": period_label,
        "period_label": "Reporting week",
        "date_generated": date.today().isoformat(),
        "reviewer": profile.get("reviewer", ""),
        "items_reviewed": analysed,
        "failures": failures,
        "thresholds": profile.get("thresholds", {}),
        "source_label": "MHRA",
        "report_title": "MHRA Alerts and Updates Weekly Review",
        "prepared_by": "MHRA Safety Monitoring Agent",
        "relevance_label": profile.get("relevance_label") or (
            "Primary care relevance" if profile.get("audience", "primary_care") == "primary_care"
            else f"{profile['practice_name']} relevance"
        ),
        "concise_excluded": profile.get("audience", "primary_care") != "primary_care",
    }

    period_name = f"Week ending {end.isoformat()}" if args.days == 7 else f"{args.days} days ending {end.isoformat()}"
    title = f"MHRA Alerts and Updates Weekly Review - {period_name} - {profile['practice_name']}"
    json_path = out_dir / f"{title}.json"
    md_path = out_dir / f"{title}.md"
    docx_path = out_dir / f"{title}.docx"

    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(build_markdown_report(report), encoding="utf-8")
    build_docx_report(report, docx_path, profile)

    google_doc = None
    if not args.no_google:
        if profile.get("storage") == "pending_sharepoint":
            google_doc = {"created": False, "mode": "skipped", "reason": "SharePoint destination not configured yet; local files only."}
        else:
            # MHRA reports can go to their own Drive folder, separate from NICE.
            drive_profile = {
                **profile,
                "destination_drive_folder_id": profile.get("mhra_destination_drive_folder_id")
                or profile.get("destination_drive_folder_id"),
            }
            # A Google failure (expired token, API outage) must not lose the run:
            # the local artefacts already exist and the email can still report it.
            try:
                google_doc = create_native_google_doc_report(report, title, drive_profile)
            except Exception as exc:
                google_doc = {"created": False, "mode": "failed", "reason": str(exc)}
                failures.append(f"Google Doc creation failed: {exc}")

    high_actions = [
        action for item in analysed
        for action in item.get("required_actions", [])
        if action.get("priority") in {"high", "urgent"}
    ]

    summary = {
        "title": title,
        "practice": profile["practice_name"],
        "month": period_label,
        "items_reviewed": len(analysed),
        "included": sum(1 for i in analysed if i.get("included")),
        "excluded": sum(1 for i in analysed if not i.get("included")),
        "high_priority_actions": high_actions,
        "markdown": str(md_path),
        "docx": str(docx_path),
        "json": str(json_path),
        "google_doc": google_doc,
        "failures": failures,
        "monitor_label": "MHRA alerts and updates",
    }
    if args.no_email:
        summary["email_notification_sent_to"] = None
    else:
        try:
            summary["email_notification_sent_to"] = send_completion_email(summary, profile)
        except Exception as exc:
            summary["email_notification_error"] = str(exc)
    return summary


if __name__ == "__main__":
    main()
