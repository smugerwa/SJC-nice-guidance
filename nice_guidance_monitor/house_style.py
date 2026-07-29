"""Single source of truth for report presentation.

The look is taken from the practice tutorial-handout house style: a left-aligned
navy title over a hairline rule, mid-blue section headings, small dense Calibri
body text, borderless metadata tables with alternating pale-blue banding, and a
small grey footer carrying the document label and page number.

DOCX, HTML and Google Docs renderers all read their colours, fonts and metrics
from here so the three artefacts stay visually identical.
"""

from __future__ import annotations

# --- Palette (hex, no leading hash: DOCX shading and HTML both need the raw pair) ---
TITLE_NAVY = "1F3864"
HEADING_BLUE = "1F6FB2"
SUBHEAD_NAVY = "1F3864"
BODY_TEXT = "262626"
MUTED_TEXT = "5A5A5A"
TABLE_BAND = "EAF1F8"
TABLE_HEAD = "DCE6F1"
RULE = "C9D6E4"
FOOTER_TEXT = "6E6E6E"

# --- Type ---
BODY_FONT = "Calibri"
TITLE_SIZE = 18
H1_SIZE = 12.5
H2_SIZE = 10.5
H3_SIZE = 10
BODY_SIZE = 10.5
META_SIZE = 9.5
TABLE_SIZE = 9
FOOTER_SIZE = 8
NOTE_SIZE = 8.5

# --- Page metrics (inches) ---
MARGIN_TOP = 0.8
MARGIN_BOTTOM = 0.8
MARGIN_LEFT = 0.9
MARGIN_RIGHT = 0.9
CONTENT_WIDTH = 6.7

# Hairline weight for paragraph and table rules, in eighths of a point.
RULE_WEIGHT = 6


def hex_to_rgb_floats(value: str) -> dict:
    """Return a Google Docs API rgbColor dict for a six-digit hex colour."""
    value = value.lstrip("#")
    return {
        "red": int(value[0:2], 16) / 255,
        "green": int(value[2:4], 16) / 255,
        "blue": int(value[4:6], 16) / 255,
    }


def docx_color(value: str):
    """Return a python-docx RGBColor for a six-digit hex colour."""
    from docx.shared import RGBColor

    return RGBColor.from_string(value.lstrip("#").upper())


def css_color(value: str) -> str:
    return f"#{value.lstrip('#')}"


# ---------------------------------------------------------------------------
# DOCX helpers
# ---------------------------------------------------------------------------


def _element(tag: str, **attrs):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    node = OxmlElement(tag)
    for key, value in attrs.items():
        node.set(qn(f"w:{key}"), value)
    return node


def set_paragraph_rule(paragraph, edge: str = "bottom", color: str = RULE, weight: int = RULE_WEIGHT, space: int = 4) -> None:
    """Draw a hairline above or below a paragraph, used for section separators."""
    from docx.oxml.ns import qn

    p_pr = paragraph._p.get_or_add_pPr()
    borders = p_pr.find(qn("w:pBdr"))
    if borders is None:
        borders = _element("w:pBdr")
        p_pr.append(borders)
    border = _element(
        f"w:{edge}",
        val="single",
        sz=str(weight),
        space=str(space),
        color=color.lstrip("#").upper(),
    )
    borders.append(border)


def shade_cell(cell, color: str) -> None:
    from docx.oxml.ns import qn

    tc_pr = cell._tc.get_or_add_tcPr()
    existing = tc_pr.find(qn("w:shd"))
    if existing is not None:
        tc_pr.remove(existing)
    tc_pr.append(_element("w:shd", val="clear", fill=color.lstrip("#").upper()))


def set_table_rules(table, inside_color: str = RULE) -> None:
    """Strip the grid and leave only faint horizontal rules between rows."""
    from docx.oxml.ns import qn

    tbl_pr = table._tbl.tblPr
    existing = tbl_pr.find(qn("w:tblBorders"))
    if existing is not None:
        tbl_pr.remove(existing)
    borders = _element("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideV"):
        borders.append(_element(f"w:{edge}", val="none", sz="0", space="0", color="auto"))
    borders.append(
        _element(
            "w:insideH",
            val="single",
            sz=str(RULE_WEIGHT),
            space="0",
            color=inside_color.lstrip("#").upper(),
        )
    )
    tbl_pr.append(borders)


def set_cell_padding(cell, top: int = 60, bottom: int = 60, left: int = 90, right: int = 90) -> None:
    """Pad a cell. Values are twentieths of a point (60 = 3pt)."""
    from docx.oxml.ns import qn

    tc_pr = cell._tc.get_or_add_tcPr()
    existing = tc_pr.find(qn("w:tcMar"))
    if existing is not None:
        tc_pr.remove(existing)
    margins = _element("w:tcMar")
    for edge, value in (("top", top), ("bottom", bottom), ("start", left), ("end", right)):
        margins.append(_element(f"w:{edge}", w=str(value), type="dxa"))
    tc_pr.append(margins)


def style_list_glyph(paragraph, color: str = HEADING_BLUE, bold: bool = True) -> None:
    """Colour the bullet or number glyph, which follows the paragraph mark formatting."""
    from docx.oxml.ns import qn

    p_pr = paragraph._p.get_or_add_pPr()
    r_pr = p_pr.find(qn("w:rPr"))
    if r_pr is None:
        r_pr = _element("w:rPr")
        p_pr.append(r_pr)
    if bold:
        r_pr.append(_element("w:b"))
    r_pr.append(_element("w:color", val=color.lstrip("#").upper()))


def add_page_number_field(paragraph) -> None:
    """Append a live PAGE field so the footer numbers itself."""
    from docx.oxml.ns import qn

    run = paragraph.add_run()
    begin = _element("w:fldChar", fldCharType="begin")
    instruction = _element("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = "PAGE"
    end = _element("w:fldChar", fldCharType="end")
    for node in (begin, instruction, end):
        run._r.append(node)
    run.font.name = BODY_FONT
    run.font.size = _pt(FOOTER_SIZE)
    run.font.color.rgb = docx_color(FOOTER_TEXT)


def _pt(size: float):
    from docx.shared import Pt

    return Pt(size)


# ---------------------------------------------------------------------------
# HTML stylesheet
# ---------------------------------------------------------------------------


def html_stylesheet() -> str:
    """Print-ready CSS mirroring the DOCX house style."""
    return f"""
:root {{
  --title-navy: {css_color(TITLE_NAVY)};
  --heading-blue: {css_color(HEADING_BLUE)};
  --subhead-navy: {css_color(SUBHEAD_NAVY)};
  --body-text: {css_color(BODY_TEXT)};
  --muted-text: {css_color(MUTED_TEXT)};
  --table-band: {css_color(TABLE_BAND)};
  --table-head: {css_color(TABLE_HEAD)};
  --rule: {css_color(RULE)};
  --footer-text: {css_color(FOOTER_TEXT)};
}}
@page {{ size: A4; margin: {MARGIN_TOP}in {MARGIN_RIGHT}in {MARGIN_BOTTOM}in {MARGIN_LEFT}in; }}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  padding: {MARGIN_TOP}in {MARGIN_RIGHT}in {MARGIN_BOTTOM}in {MARGIN_LEFT}in;
  max-width: 8.27in;
  font-family: Calibri, "Segoe UI", Carlito, system-ui, sans-serif;
  font-size: {BODY_SIZE}pt;
  line-height: 1.45;
  color: var(--body-text);
  background: #ffffff;
}}
h1.doc-title {{
  margin: 0 0 6pt;
  padding-bottom: 6pt;
  border-bottom: 0.75pt solid var(--rule);
  font-size: {TITLE_SIZE}pt;
  font-weight: 700;
  color: var(--title-navy);
  letter-spacing: -0.2pt;
}}
p.doc-subtitle {{
  margin: 10pt 0 2pt;
  font-size: {H1_SIZE}pt;
  font-weight: 700;
  color: var(--heading-blue);
}}
p.doc-org {{
  margin: 0 0 12pt;
  font-size: {BODY_SIZE}pt;
  font-weight: 700;
  color: var(--subhead-navy);
}}
h2 {{
  margin: 20pt 0 6pt;
  font-size: {H1_SIZE}pt;
  font-weight: 700;
  color: var(--heading-blue);
  page-break-after: avoid;
}}
h3 {{
  margin: 14pt 0 4pt;
  font-size: {H2_SIZE}pt;
  font-weight: 700;
  color: var(--subhead-navy);
  page-break-after: avoid;
}}
h4 {{
  margin: 10pt 0 3pt;
  font-size: {H3_SIZE}pt;
  font-weight: 700;
  color: var(--subhead-navy);
  page-break-after: avoid;
}}
p {{ margin: 0 0 7pt; }}
a {{ color: var(--heading-blue); }}
hr.section-rule {{
  border: 0;
  border-top: 0.75pt solid var(--rule);
  margin: 18pt 0;
}}
ul, ol {{ margin: 0 0 8pt; padding-left: 18pt; }}
li {{ margin-bottom: 3pt; }}
li::marker {{ color: var(--heading-blue); font-weight: 700; }}
.label {{ font-weight: 700; color: var(--subhead-navy); }}
.table-scroll {{ overflow-x: auto; margin: 0 0 14pt; }}
table {{
  width: 100%;
  border-collapse: collapse;
  font-size: {TABLE_SIZE}pt;
}}
table.meta {{
  font-size: {META_SIZE}pt;
  margin-bottom: 16pt;
}}
table.meta th {{
  width: 24%;
  text-align: left;
  font-weight: 700;
  color: var(--subhead-navy);
}}
table.meta th, table.meta td {{
  border: 0;
  padding: 5pt 8pt;
  vertical-align: top;
}}
table.meta tr:nth-child(odd) th, table.meta tr:nth-child(odd) td {{
  background: var(--table-band);
}}
table.data th {{
  text-align: left;
  font-weight: 700;
  color: var(--title-navy);
  background: var(--table-head);
  padding: 5pt 8pt;
  border: 0;
}}
table.data td {{
  padding: 5pt 8pt;
  vertical-align: top;
  border: 0;
  border-top: 0.75pt solid var(--rule);
}}
table.data tbody tr:nth-child(even) td {{ background: var(--table-band); }}
td.score {{ text-align: right; white-space: nowrap; }}
.doc-footer {{
  margin-top: 24pt;
  padding-top: 6pt;
  border-top: 0.75pt solid var(--rule);
  display: flex;
  justify-content: space-between;
  gap: 12pt;
  font-size: {FOOTER_SIZE}pt;
  color: var(--footer-text);
}}
.note {{
  margin-top: 10pt;
  font-size: {NOTE_SIZE}pt;
  font-style: italic;
  color: var(--muted-text);
}}
@media (max-width: 640px) {{
  body {{ padding: 16px; }}
  .doc-footer {{ flex-direction: column; gap: 4pt; }}
}}
@media print {{
  body {{ padding: 0; max-width: none; }}
}}
""".strip()
