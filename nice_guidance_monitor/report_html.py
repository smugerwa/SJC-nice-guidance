"""Print-ready HTML rendering of the governance report.

Useful on the VPS: the file can be served over nginx, opened in a browser and
printed to PDF, or pasted into an email, and it carries the same house style as
the DOCX and Google Doc.
"""

from __future__ import annotations

from html import escape

from . import house_style as hs
from .report import partition_items, report_meta_pairs, report_subtitle, _item_reference


def build_html_report(report: dict) -> str:
    source_label = report.get("source_label", "NICE")
    report_title = report.get("report_title", f"{source_label} Guidance Monthly Review")
    buckets = partition_items(report)
    excluded = buckets["excluded"]
    clinically_relevant = buckets["clinically_relevant"]
    high_min = buckets["high_min"]

    parts: list[str] = [
        "<!doctype html>",
        '<html lang="en-GB">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{escape(report_title)} - {escape(report['month_label'])} - {escape(report['practice_name'])}</title>",
        f"<style>{hs.html_stylesheet()}</style>",
        "</head>",
        "<body>",
        f'<h1 class="doc-title">{escape(report_title)} &mdash; {escape(report["month_label"])}</h1>',
        f'<p class="doc-subtitle">{escape(report_subtitle(report))}</p>',
        f'<p class="doc-org">{escape(report["practice_name"])}</p>',
        _meta_table(report),
        "<h2>Executive summary</h2>",
        "<ul>",
        f"<li>{escape(source_label)} items reviewed: {len(report['items_reviewed'])}</li>",
        f"<li>Included in clinical brief: {len(clinically_relevant)}</li>",
        f"<li>Excluded or appendix only: {len(excluded)}</li>",
        f"<li>High or very high primary care relevance: {len(buckets['high'])}</li>",
        "</ul>",
        "<h3>Key points for clinical meeting</h3>",
    ]

    if clinically_relevant:
        parts.append("<ol>")
        for item in clinically_relevant[:6]:
            ident = item["guidance_identification"]
            brief = item.get("clinical_brief", {})
            label = f"{_item_reference(ident)} - {ident.get('title', '')}"
            parts.append(
                f'<li><span class="label">{escape(label)}:</span> '
                f"{escape(_clean(brief.get('what_changed', '')))}</li>"
            )
        parts.append("</ol>")
    else:
        parts.append("<p>No clinically relevant updates identified for routine primary care.</p>")

    parts.append('<hr class="section-rule">')
    parts.append("<h2>Action dashboard</h2>")
    action_rows = []
    for item in clinically_relevant:
        ident = item["guidance_identification"]
        brief = item.get("clinical_brief", {})
        action_rows.append([
            _link(ident.get("url"), f"{_item_reference(ident)} - {ident.get('title', '')}"),
            (escape(str(item.get("relevance", {}).get("score", ""))), "score"),
            escape(_clean(brief.get("suggested_action", ""))),
            escape(_clean(brief.get("meeting_discussion", ""))),
        ])
    parts.append(
        _data_table(
            [f"{source_label} item", "Score", "What to do", "Meeting question"],
            action_rows,
            empty_message="No items met the clinical relevance threshold.",
        )
    )

    parts.append('<hr class="section-rule">')
    parts.append("<h2>Clinical update briefs</h2>")
    for item in clinically_relevant:
        ident = item["guidance_identification"]
        brief = item.get("clinical_brief", {})
        relevance = item.get("relevance", {})
        brief_heading = f"{_item_reference(ident)} - {ident.get('title', '')}"
        parts.append(f"<h3>{escape(brief_heading)}</h3>")
        parts.append("<ul>")
        parts.append(_label_line("Type", ident.get("guidance_type", "")))
        parts.append(_label_line("Date", ident.get("publication_or_update_date", "")))
        parts.append(_label_line("Status", ident.get("status", "")))
        parts.append(_label_line("Primary care relevance", f"{relevance.get('score', '')}/5 - {relevance.get('rationale', '')}"))
        if ident.get("url"):
            parts.append(f'<li><span class="label">{escape(source_label)} source:</span> {_link(ident.get("url"), ident.get("url"))}</li>')
        parts.append("</ul>")

        parts.append("<h4>What changed or matters</h4>")
        parts.append(f"<p>{escape(_clean(brief.get('what_changed', '')))}</p>")
        takeaways = brief.get("key_takeaways") or item.get("key_clinical_points", [])[:5]
        if takeaways:
            parts.append("<h4>Key takeaways for clinicians</h4>")
            parts.append("<ul>")
            parts += [f"<li>{escape(_clean(str(point)))}</li>" for point in takeaways]
            parts.append("</ul>")
        parts.append("<h4>Practice implication</h4>")
        parts.append(f"<p>{escape(_clean(brief.get('practice_implication', '')))}</p>")
        parts.append("<h4>Suggested meeting discussion</h4>")
        parts.append(f"<p>{escape(_clean(brief.get('meeting_discussion', '')))}</p>")
        parts.append("<h4>Suggested action</h4>")
        parts.append(f"<p>{escape(_clean(brief.get('suggested_action', '')))}</p>")

    parts.append('<hr class="section-rule">')
    parts.append("<h2>Items for clinical meeting</h2>")
    meeting_rows = []
    for item in clinically_relevant:
        ident = item["guidance_identification"]
        score = item.get("relevance", {}).get("score", 0)
        meeting_rows.append([
            escape("Decision" if score >= high_min else "Discussion"),
            escape(f"{_item_reference(ident)} - {ident.get('title', '')}"),
            escape(_clean(item.get("clinical_brief", {}).get("meeting_discussion", ""))),
        ])
    parts.append(_data_table(["Type", "Item", "Meeting prompt"], meeting_rows, empty_message="None"))

    parts.append('<hr class="section-rule">')
    parts.append(f"<h2>Appendix A: low-relevance or excluded {escape(source_label)} items</h2>")
    appendix_rows = []
    for item in excluded:
        ident = item["guidance_identification"]
        appendix_rows.append([
            escape(_item_reference(ident)),
            escape(ident.get("title", "")),
            escape(_clean(item.get("exclusion_reason", ""))),
        ])
    for item in buckets["low_relevance"]:
        ident = item["guidance_identification"]
        appendix_rows.append([
            escape(_item_reference(ident)),
            escape(ident.get("title", "")),
            "Low primary care relevance; awareness only.",
        ])
    parts.append(_data_table(["Reference", "Title", "Reason"], appendix_rows, empty_message="None"))

    parts.append(f"<h2>Appendix B: main {escape(source_label)} sources</h2>")
    source_rows = []
    for item in report["items_reviewed"]:
        ident = item.get("guidance_identification", {})
        if ident.get("url"):
            source_rows.append([
                escape(_item_reference(ident)),
                escape(ident.get("title", "")),
                _link(ident.get("url"), ident.get("url")),
            ])
    parts.append(_data_table(["Reference", "Guidance", "URL"], source_rows, empty_message="None"))

    if report.get("failures"):
        parts.append('<hr class="section-rule">')
        parts.append("<h2>Source retrieval failures</h2>")
        parts.append("<ul>")
        parts += [f"<li>{escape(str(failure))}</li>" for failure in report["failures"]]
        parts.append("</ul>")

    parts += [
        '<div class="doc-footer">',
        f'<span>{escape(report_title)}: {escape(report["month_label"])} &nbsp;|&nbsp; {escape(report["practice_name"])}</span>',
        f'<span>Generated {escape(report["date_generated"])}</span>',
        "</div>",
        '<p class="note">Clinical governance document &mdash; for internal use. Full linked-source extraction is '
        "retained in the JSON source log for audit, but omitted from this meeting brief for readability.</p>",
        "</body>",
        "</html>",
    ]
    return "\n".join(parts)


def _meta_table(report: dict) -> str:
    rows = [
        f"<tr><th>{escape(label)}</th><td>{escape(str(value or ''))}</td></tr>"
        for label, value in report_meta_pairs(report)
    ]
    return '<table class="meta">' + "".join(rows) + "</table>"


def _data_table(headers: list[str], rows: list[list], empty_message: str) -> str:
    head = "".join(f"<th>{escape(header)}</th>" for header in headers)
    if rows:
        body = []
        for row in rows:
            cells = []
            for cell in row:
                if isinstance(cell, tuple):
                    value, css_class = cell
                    cells.append(f'<td class="{css_class}">{value}</td>')
                else:
                    cells.append(f"<td>{cell}</td>")
            body.append("<tr>" + "".join(cells) + "</tr>")
        body_html = "".join(body)
    else:
        body_html = f'<tr><td colspan="{len(headers)}">{escape(empty_message)}</td></tr>'
    return (
        '<div class="table-scroll"><table class="data"><thead><tr>'
        + head
        + "</tr></thead><tbody>"
        + body_html
        + "</tbody></table></div>"
    )


def _label_line(label: str, value: object) -> str:
    return f'<li><span class="label">{escape(label)}:</span> {escape(_clean(str(value or "")))}</li>'


def _link(url: object, text: object) -> str:
    text_html = escape(str(text or ""))
    if not url:
        return text_html
    return f'<a href="{escape(str(url))}">{text_html}</a>'


def _clean(value: object) -> str:
    return str(value or "").replace("**", "").strip()
