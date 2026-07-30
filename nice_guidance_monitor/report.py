from __future__ import annotations

import re
from pathlib import Path

from . import house_style as hs


def report_subtitle(report: dict) -> str:
    """Descriptive blue subtitle line, matching the house style handout layout."""
    source_label = report.get("source_label", "NICE")
    period_label = report.get("period_label", "Reporting month").lower()
    if source_label == "MHRA":
        return f"MHRA alerts, recalls and safety information reviewed for the {period_label}"
    return f"{source_label} guidance published or updated in the {period_label}, reviewed for UK primary care"


def report_meta_pairs(report: dict) -> list[tuple[str, str]]:
    """Label/value pairs for the banded metadata table shared by every renderer."""
    source_label = report.get("source_label", "NICE")
    period_label = report.get("period_label", "Reporting month")
    prepared_by = report.get("prepared_by", f"{source_label} Guidance Monitoring Agent")
    return [
        (period_label, report["month_label"]),
        ("Date generated", report["date_generated"]),
        ("Prepared by", prepared_by),
        ("Reviewed by", report.get("reviewer") or "[INSERT NAME/ROLE]"),
        ("Source of truth", f"{source_label} published pages and linked source documents"),
        ("Status", "Clinical governance document - for internal use"),
    ]


def partition_items(report: dict) -> dict:
    """Split reviewed items into the buckets every renderer needs."""
    items = report["items_reviewed"]
    included = sorted(
        (i for i in items if i.get("included")),
        key=lambda item: item.get("relevance", {}).get("score", 0),
        reverse=True,
    )
    excluded = [i for i in items if not i.get("included")]
    high_min = report.get("thresholds", {}).get("high_relevance_min_score", 4)
    clinically_relevant = [i for i in included if i.get("relevance", {}).get("score", 0) >= 3]
    return {
        "included": included,
        "excluded": excluded,
        "clinically_relevant": clinically_relevant,
        "low_relevance": [i for i in included if i.get("relevance", {}).get("score", 0) < 3],
        "high": [i for i in clinically_relevant if i.get("relevance", {}).get("score", 0) >= high_min],
        "high_min": high_min,
    }


def build_markdown_report(report: dict) -> str:
    source_label = report.get("source_label", "NICE")
    report_title = report.get("report_title", f"{source_label} Guidance Monthly Review")
    period_label = report.get("period_label", "Reporting month")
    prepared_by = report.get("prepared_by", f"{source_label} Guidance Monitoring Agent")
    buckets = partition_items(report)
    included = buckets["included"]
    excluded = buckets["excluded"]
    high_min = buckets["high_min"]
    high = [i for i in included if i.get("relevance", {}).get("score", 0) >= high_min]

    lines = [
        f"# {report_title} - {report['month_label']} - {report['practice_name']}",
        "",
        f"**{period_label}:** {report['month_label']}",
        f"**Date generated:** {report['date_generated']}",
        f"**Prepared by:** {prepared_by}",
        f"**Reviewed by:** {report.get('reviewer') or '[INSERT NAME/ROLE]'}",
        "",
        "## Executive summary",
        "",
        f"- {source_label} items reviewed: {len(report['items_reviewed'])}",
        f"- Included in detailed review: {len(included)}",
        f"- Excluded or appendix only: {len(excluded)}",
        f"- High or very high primary care relevance: {len(high)}",
        "",
    ]

    clinically_relevant = buckets["clinically_relevant"]
    lines += ["### Key points for clinical meeting", ""]
    for item in clinically_relevant[:6]:
        ident = item["guidance_identification"]
        brief = item.get("clinical_brief", {})
        lines.append(f"- **{_item_reference(ident)} - {ident.get('title')}:** {brief.get('what_changed', '').strip()}")
    if not clinically_relevant:
        lines.append("- No clinically relevant updates identified for routine primary care.")
    lines.append("")

    lines += [
        "## Action dashboard",
        "",
        f"| {source_label} item | Relevance | What to do | Meeting question |",
        "| --- | ---: | --- | --- |",
    ]
    for item in clinically_relevant:
        ident = item["guidance_identification"]
        brief = item.get("clinical_brief", {})
        lines.append(
            f"| [{_item_reference(ident)} - {ident.get('title')}]({ident.get('url')}) "
            f"| {item.get('relevance', {}).get('score', '')} "
            f"| {brief.get('suggested_action', '')} "
            f"| {brief.get('meeting_discussion', '')} |"
        )
    lines.append("")

    lines += ["## Clinical Update Briefs", ""]
    for item in clinically_relevant:
        ident = item["guidance_identification"]
        brief = item.get("clinical_brief", {})
        lines += [
            f"### {_item_reference(ident)} - {ident.get('title')}",
            "",
            f"- **Type:** {ident.get('guidance_type', '')}",
            f"- **Date:** {ident.get('publication_or_update_date', '')}",
            f"- **Status:** {ident.get('status', '')}",
            f"- **Primary care relevance:** {item.get('relevance', {}).get('score', '')}/5 - {item.get('relevance', {}).get('rationale', '')}",
            f"- **{source_label} source:** {ident.get('url', '')}",
            "",
            "#### What changed or matters",
            "",
            brief.get("what_changed", ""),
            "",
            "#### Key takeaways for clinicians",
            "",
        ]
        takeaways = brief.get("key_takeaways") or item.get("key_clinical_points", [])[:5]
        lines += [f"- {point}" for point in takeaways]
        lines += [
            "",
            "#### Practice implication",
            "",
            brief.get("practice_implication", ""),
            "",
            "#### Suggested meeting discussion",
            "",
            f"- {brief.get('meeting_discussion', '')}",
            "",
            "#### Suggested action",
            "",
            f"- {brief.get('suggested_action', '')}",
            "",
        ]

    lines += ["## Items for clinical meeting", ""]
    discussion = []
    decisions = []
    awareness = []
    for item in clinically_relevant:
        ident = item["guidance_identification"]
        score = item.get("relevance", {}).get("score", 0)
        label = f"{_item_reference(ident)} - {ident.get('title')}: {item.get('clinical_brief', {}).get('meeting_discussion', '')}"
        if score >= high_min:
            decisions.append(label)
        elif score >= 3:
            discussion.append(label)
        else:
            awareness.append(label)
    lines += ["**Items requiring discussion:**"] + ([f"- {x}" for x in discussion] or ["- None"])
    lines += ["", "**Items requiring decision:**"] + ([f"- {x}" for x in decisions] or ["- None"])
    lines += ["", "**Items for awareness only:**"] + ([f"- {x}" for x in awareness] or ["- None"])
    lines.append("")

    low_relevance = buckets["low_relevance"]
    lines += [f"## Appendix A: Low-Relevance Or Excluded {source_label} Items", ""]
    lines += [f"| Title | {source_label} reference | URL | Reason excluded |", "| --- | --- | --- | --- |"]
    for item in excluded:
        ident = item["guidance_identification"]
        lines.append(f"| {ident.get('title')} | {_item_reference(ident)} | {ident.get('url')} | {item.get('exclusion_reason', '')} |")
    for item in low_relevance:
        ident = item["guidance_identification"]
        lines.append(f"| {ident.get('title')} | {_item_reference(ident)} | {ident.get('url')} | Low primary care relevance; awareness only. |")
    if not excluded and not low_relevance:
        lines.append("| None |  |  |  |")
    lines.append("")

    lines += [f"## Appendix B: Main {source_label} Sources", ""]
    for item in report["items_reviewed"]:
        ident = item.get("guidance_identification", {})
        if ident.get("url"):
            lines.append(f"- {_item_reference(ident)} - {ident.get('title')}: {ident.get('url')}")
    if report.get("failures"):
        lines += ["", "## Source retrieval failures", ""]
        lines += [f"- {failure}" for failure in report["failures"]]
    lines += ["", "_Clinical governance document - for internal use._", ""]
    lines += ["", "_Full linked-source extraction is retained in the JSON source log for audit, but omitted from this meeting brief for readability._", ""]
    return "\n".join(lines)


def build_docx_report(report: dict, path: Path, config: dict) -> None:
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Inches, Pt
    except ImportError:
        return
    source_label = report.get("source_label", "NICE")
    report_title = report.get("report_title", f"{source_label} Guidance Monthly Review")

    template = config.get("headed_paper_template_docx")
    doc = Document(template) if template and Path(template).exists() else Document()
    section = doc.sections[0]
    section.top_margin = Inches(hs.MARGIN_TOP)
    section.bottom_margin = Inches(hs.MARGIN_BOTTOM)
    section.left_margin = Inches(hs.MARGIN_LEFT)
    section.right_margin = Inches(hs.MARGIN_RIGHT)

    _setup_docx_styles(doc)
    _build_footer(doc, section, report, report_title)

    buckets = partition_items(report)
    included = buckets["included"]
    excluded = buckets["excluded"]
    clinically_relevant = buckets["clinically_relevant"]
    high = buckets["high"]
    high_min = buckets["high_min"]

    # Title block: navy title over a hairline, blue descriptive subtitle, bold practice line.
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    title.paragraph_format.space_after = Pt(6)
    run = title.add_run(f"{report_title} - {report['month_label']}")
    run.bold = True
    run.font.size = Pt(hs.TITLE_SIZE)
    run.font.name = hs.BODY_FONT
    run.font.color.rgb = hs.docx_color(hs.TITLE_NAVY)
    hs.set_paragraph_rule(title, "bottom")

    subtitle = doc.add_paragraph()
    subtitle.paragraph_format.space_before = Pt(10)
    subtitle.paragraph_format.space_after = Pt(2)
    subtitle_run = subtitle.add_run(report_subtitle(report))
    subtitle_run.bold = True
    subtitle_run.font.size = Pt(hs.H1_SIZE)
    subtitle_run.font.name = hs.BODY_FONT
    subtitle_run.font.color.rgb = hs.docx_color(hs.HEADING_BLUE)

    org = doc.add_paragraph()
    org.paragraph_format.space_after = Pt(12)
    org_run = org.add_run(report["practice_name"])
    org_run.bold = True
    org_run.font.size = Pt(hs.BODY_SIZE)
    org_run.font.name = hs.BODY_FONT
    org_run.font.color.rgb = hs.docx_color(hs.SUBHEAD_NAVY)

    _add_meta_table(doc, report_meta_pairs(report))

    _add_section_heading(doc, "Executive Summary", rule=False)
    _add_bullet(doc, f"{source_label} items reviewed: {len(report['items_reviewed'])}")
    _add_bullet(doc, f"Included in clinical brief: {len(clinically_relevant)}")
    _add_bullet(doc, f"Excluded or appendix only: {len(excluded)}")
    _add_bullet(doc, f"High or very high primary care relevance: {len(high)}")

    doc.add_heading("Key Points For Clinical Meeting", 2)
    if clinically_relevant:
        for item in clinically_relevant[:6]:
            ident = item["guidance_identification"]
            brief = item.get("clinical_brief", {})
            p = _add_numbered(doc, "")
            _add_inline_markup(p, f"**{_item_reference(ident)} - {ident.get('title')}:** {brief.get('what_changed', '').strip()}")
    else:
        _add_bullet(doc, "No clinically relevant updates identified for routine primary care.")

    _add_section_heading(doc, "Action Dashboard")
    action_rows = []
    for item in clinically_relevant:
        ident = item["guidance_identification"]
        brief = item.get("clinical_brief", {})
        action_rows.append([
            f"{_item_reference(ident)} - {ident.get('title')}",
            str(item.get("relevance", {}).get("score", "")),
            brief.get("suggested_action", ""),
            brief.get("meeting_discussion", ""),
        ])
    _add_table(
        doc,
        [f"{source_label} item", "Score", "What to do", "Meeting question"],
        action_rows or [["No items met the clinical relevance threshold.", "", "", ""]],
        [2.15, 0.55, 2.0, 2.0],
    )

    _add_section_heading(doc, "Clinical Update Briefs")
    for item in clinically_relevant:
        ident = item["guidance_identification"]
        brief = item.get("clinical_brief", {})
        doc.add_heading(f"{_item_reference(ident)} - {ident.get('title')}", 2)
        _add_label_value(doc, "Type", ident.get("guidance_type", ""))
        _add_label_value(doc, "Date", ident.get("publication_or_update_date", ""))
        _add_label_value(doc, "Status", ident.get("status", ""))
        _add_label_value(doc, "Primary care relevance", f"{item.get('relevance', {}).get('score', '')}/5 - {item.get('relevance', {}).get('rationale', '')}")
        _add_label_value(doc, f"{source_label} source", ident.get("url", ""))

        doc.add_heading("What Changed Or Matters", 3)
        doc.add_paragraph(_clean_docx_text(brief.get("what_changed", "")))
        doc.add_heading("Key Takeaways For Clinicians", 3)
        for point in brief.get("key_takeaways") or item.get("key_clinical_points", [])[:5]:
            _add_bullet(doc, _clean_docx_text(point))
        doc.add_heading("Practice Implication", 3)
        doc.add_paragraph(_clean_docx_text(brief.get("practice_implication", "")))
        doc.add_heading("Suggested Meeting Discussion", 3)
        _add_bullet(doc, _clean_docx_text(brief.get("meeting_discussion", "")))
        doc.add_heading("Suggested Action", 3)
        _add_bullet(doc, _clean_docx_text(brief.get("suggested_action", "")))

    _add_section_heading(doc, "Items For Clinical Meeting")
    meeting_rows = []
    for item in clinically_relevant:
        ident = item["guidance_identification"]
        score = item.get("relevance", {}).get("score", 0)
        category = "Decision" if score >= high_min else "Discussion"
        meeting_rows.append([category, f"{_item_reference(ident)} - {ident.get('title')}", item.get("clinical_brief", {}).get("meeting_discussion", "")])
    _add_table(doc, ["Type", "Item", "Meeting prompt"], meeting_rows or [["None", "", ""]], [1.0, 2.6, 3.1])

    low_relevance = buckets["low_relevance"]
    _add_section_heading(doc, f"Appendix A: Low-Relevance Or Excluded {source_label} Items")
    appendix_rows = []
    for item in excluded:
        ident = item["guidance_identification"]
        appendix_rows.append([_item_reference(ident), ident.get("title", ""), item.get("exclusion_reason", "")])
    for item in low_relevance:
        ident = item["guidance_identification"]
        appendix_rows.append([_item_reference(ident), ident.get("title", ""), "Low primary care relevance; awareness only."])
    _add_table(doc, ["Reference", "Title", "Reason"], appendix_rows or [["None", "", ""]], [0.85, 3.0, 2.85])

    _add_section_heading(doc, f"Appendix B: Main {source_label} Sources")
    source_rows = []
    for item in report["items_reviewed"]:
        ident = item.get("guidance_identification", {})
        if ident.get("url"):
            source_rows.append([_item_reference(ident), ident.get("title", ""), ident.get("url", "")])
    _add_table(doc, ["Reference", "Guidance", "URL"], source_rows or [["None", "", ""]], [0.85, 2.85, 3.0])

    if report.get("failures"):
        _add_section_heading(doc, "Source Retrieval Failures")
        for failure in report["failures"]:
            _add_bullet(doc, _clean_docx_text(str(failure)))

    note = doc.add_paragraph()
    note.paragraph_format.space_before = Pt(10)
    hs.set_paragraph_rule(note, "top")
    r = note.add_run("Full linked-source extraction is retained in the JSON source log for audit, but omitted from this meeting brief for readability.")
    r.italic = True
    r.font.size = Pt(hs.NOTE_SIZE)
    r.font.name = hs.BODY_FONT
    r.font.color.rgb = hs.docx_color(hs.MUTED_TEXT)

    _finalize_docx_typography(doc)
    doc.save(path)


def _item_reference(ident: dict) -> str:
    return ident.get("source_reference") or ident.get("nice_reference") or ident.get("reference") or "MHRA"


def _build_footer(doc, section, report: dict, report_title: str) -> None:
    """Footer carrying the document label on the left and a live page number on the right."""
    from docx.enum.text import WD_TAB_ALIGNMENT
    from docx.shared import Inches, Pt

    footer = section.footer.paragraphs[0] if section.footer.paragraphs else section.footer.add_paragraph()
    for run in list(footer.runs):
        run._r.getparent().remove(run._r)
    footer.text = ""
    footer.paragraph_format.tab_stops.add_tab_stop(Inches(hs.CONTENT_WIDTH), WD_TAB_ALIGNMENT.RIGHT)
    hs.set_paragraph_rule(footer, "top")
    label = footer.add_run(f"{report_title}: {report['month_label']}  |  {report['practice_name']}\t")
    label.font.name = hs.BODY_FONT
    label.font.size = Pt(hs.FOOTER_SIZE)
    label.font.color.rgb = hs.docx_color(hs.FOOTER_TEXT)
    page_label = footer.add_run("Page ")
    page_label.font.name = hs.BODY_FONT
    page_label.font.size = Pt(hs.FOOTER_SIZE)
    page_label.font.color.rgb = hs.docx_color(hs.FOOTER_TEXT)
    hs.add_page_number_field(footer)


def _setup_docx_styles(doc) -> None:
    from docx.shared import Pt

    for style_name, size, color, bold in [
        ("Normal", hs.BODY_SIZE, hs.BODY_TEXT, False),
        ("Heading 1", hs.H1_SIZE, hs.HEADING_BLUE, True),
        ("Heading 2", hs.H2_SIZE, hs.SUBHEAD_NAVY, True),
        ("Heading 3", hs.H3_SIZE, hs.SUBHEAD_NAVY, True),
    ]:
        style = _get_style_case_insensitive(doc, style_name)
        if style:
            style.font.name = hs.BODY_FONT
            style.font.size = Pt(size)
            style.font.color.rgb = hs.docx_color(color)
            style.font.bold = bold


def _get_style_case_insensitive(doc, style_name: str):
    for style in doc.styles:
        if style.name.lower() == style_name.lower():
            return style
    return None


def _heading_spec(style_name: str) -> tuple[float, str]:
    if style_name == "heading 1":
        return hs.H1_SIZE, hs.HEADING_BLUE
    if style_name == "heading 2":
        return hs.H2_SIZE, hs.SUBHEAD_NAVY
    return hs.H3_SIZE, hs.SUBHEAD_NAVY


def _finalize_docx_typography(doc) -> None:
    from docx.shared import Pt

    body = hs.docx_color(hs.BODY_TEXT)
    for paragraph in doc.paragraphs:
        style_name = paragraph.style.name.lower()
        for run in paragraph.runs:
            if not run.text:
                continue
            if not run.font.name:
                run.font.name = hs.BODY_FONT
            if style_name.startswith("heading"):
                size, color = _heading_spec(style_name)
                run.font.size = Pt(size)
                run.font.color.rgb = hs.docx_color(color)
                run.bold = True
            elif not run.font.size:
                run.font.size = Pt(hs.BODY_SIZE)
                run.font.color.rgb = body
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        if not run.font.name:
                            run.font.name = hs.BODY_FONT


def _add_section_heading(doc, text: str, rule: bool = True):
    """Top-level heading, preceded by a full-width hairline like the house style handout."""
    from docx.shared import Pt

    if rule:
        spacer = doc.add_paragraph()
        spacer.paragraph_format.space_before = Pt(12)
        spacer.paragraph_format.space_after = Pt(0)
        hs.set_paragraph_rule(spacer, "bottom")
    heading = doc.add_heading(text, 1)
    heading.paragraph_format.space_before = Pt(10)
    heading.paragraph_format.space_after = Pt(6)
    return heading


def _add_meta_table(doc, pairs: list[tuple[str, str]]):
    """Borderless two-column table with alternating pale-blue banding and no header row."""
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
    from docx.shared import Inches, Pt

    label_width = 1.65
    value_width = hs.CONTENT_WIDTH - label_width
    table = doc.add_table(rows=0, cols=2)
    table.autofit = False
    hs.set_table_rules(table, inside_color="FFFFFF")
    for index, (label, value) in enumerate(pairs):
        cells = table.add_row().cells
        for cell_index, text in enumerate((label, str(value or ""))):
            cell = cells[cell_index]
            cell.text = _clean_docx_text(text)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
            cell.width = Inches(label_width if cell_index == 0 else value_width)
            hs.set_cell_padding(cell)
            if index % 2 == 0:
                hs.shade_cell(cell, hs.TABLE_BAND)
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after = Pt(0)
                for run in paragraph.runs:
                    run.font.name = hs.BODY_FONT
                    run.font.size = Pt(hs.META_SIZE)
                    if cell_index == 0:
                        run.bold = True
                        run.font.color.rgb = hs.docx_color(hs.SUBHEAD_NAVY)
                    else:
                        run.font.color.rgb = hs.docx_color(hs.BODY_TEXT)
    trailing = doc.add_paragraph()
    trailing.paragraph_format.space_after = Pt(4)
    return table


def _add_table(doc, headers: list[str], rows: list[list[str]], widths: list[float]):
    """Data table: shaded header, banded rows, hairline row rules, no outer grid."""
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
    from docx.shared import Inches, Pt

    table = doc.add_table(rows=1, cols=len(headers))
    table.autofit = False
    hs.set_table_rules(table)
    for idx, header in enumerate(headers):
        cell = table.rows[0].cells[idx]
        cell.text = _clean_docx_text(header)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        hs.shade_cell(cell, hs.TABLE_HEAD)
        hs.set_cell_padding(cell)
        for paragraph in cell.paragraphs:
            paragraph.paragraph_format.space_after = Pt(0)
            for run in paragraph.runs:
                run.bold = True
                run.font.name = hs.BODY_FONT
                run.font.size = Pt(hs.TABLE_SIZE)
                run.font.color.rgb = hs.docx_color(hs.TITLE_NAVY)
    for row_index, row in enumerate(rows):
        cells = table.add_row().cells
        for idx, value in enumerate(row):
            cell = cells[idx]
            cell.text = _clean_docx_text(str(value or ""))
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
            hs.set_cell_padding(cell)
            if row_index % 2 == 1:
                hs.shade_cell(cell, hs.TABLE_BAND)
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after = Pt(0)
                for run in paragraph.runs:
                    run.font.name = hs.BODY_FONT
                    run.font.size = Pt(hs.TABLE_SIZE)
                    run.font.color.rgb = hs.docx_color(hs.BODY_TEXT)
    for row in table.rows:
        for idx, width in enumerate(widths):
            if idx < len(row.cells):
                row.cells[idx].width = Inches(width)
    trailing = doc.add_paragraph()
    trailing.paragraph_format.space_after = Pt(4)
    return table


def _add_bullet(doc, text: str):
    paragraph = _add_list_paragraph(doc, "List Bullet", "• ")
    if text:
        _add_inline_markup(paragraph, text)
    return paragraph


def _add_numbered(doc, text: str):
    paragraph = _add_list_paragraph(doc, "List Number", "")
    if text:
        _add_inline_markup(paragraph, text)
    return paragraph


def _add_list_paragraph(doc, style_name: str, fallback_prefix: str):
    from docx.shared import Pt

    try:
        paragraph = doc.add_paragraph(style=style_name)
    except KeyError:
        paragraph = doc.add_paragraph()
        if fallback_prefix:
            paragraph.add_run(fallback_prefix)
    paragraph.paragraph_format.space_after = Pt(3)
    hs.style_list_glyph(paragraph)
    return paragraph


def _add_label_value(doc, label: str, value: str):
    from docx.shared import Pt

    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(2)
    label_run = paragraph.add_run(f"{label}: ")
    label_run.bold = True
    label_run.font.color.rgb = hs.docx_color(hs.SUBHEAD_NAVY)
    _add_inline_markup(paragraph, value)
    return paragraph


def _add_inline_markup(paragraph, text: str) -> None:
    # Keep the ** markers through cleaning so they can still be turned into bold runs.
    text = _clean_docx_text(text, keep_markup=True)
    for part in re.split(r"(\*\*.*?\*\*)", text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        else:
            paragraph.add_run(part)


def _clean_docx_text(text: str, keep_markup: bool = False) -> str:
    replacements = {
        "â€“": "-",
        "â€”": "-",
        "â€™": "'",
        "â€˜": "'",
        "â€œ": '"',
        # The full closing-quote sequence, not the bare "â€" prefix, which would
        # leave the trailing \x9d behind in the output.
        "â€\x9d": '"',
        "Â": "",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    if not keep_markup:
        text = text.replace("**", "")
    return text.strip()
