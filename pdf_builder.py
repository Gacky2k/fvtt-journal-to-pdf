from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, List
import hashlib

from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, PageBreak, Spacer, Table, TableStyle
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from xml.sax.saxutils import escape

def _fmt(text: str) -> str:
    """Escape text for ReportLab Paragraph, but allow simple bold markers [[B]]..[[/B]]."""
    s = escape(text or "")
    return s.replace("[[B]]", "<b>").replace("[[/B]]", "</b>")



@dataclass
class Selection:
    """Selection for multi-journal builds.

    items: List of (journal_title, page_title, heading_title_or_None)

    - heading_title = None  => include whole page (preface + all headings)
    - heading_title = str   => include only that heading within that page
    """
    items: List[Tuple[str, str, Optional[str]]]


def _key_for(s: str) -> str:
    h = hashlib.md5(s.encode("utf-8")).hexdigest()[:10]
    return f"sec-{h}"


class DocWithTOC(SimpleDocTemplate):
    def __init__(self, *args, toc_key: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.toc_key = toc_key

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and hasattr(flowable, "_bookmarkName"):
            lvl = getattr(flowable, "_tocLevel", None)
            if lvl is None:
                return
            self.notify("TOCEntry", (lvl, flowable._headingText, self.page, flowable._bookmarkName))


def _heading(text: str, style: ParagraphStyle, path: str, toc_level: Optional[int] = None) -> Paragraph:
    key = _key_for(path)
    p = Paragraph(f'<a name="{key}"/>{escape(text)}', style)
    p._bookmarkName = key
    p._headingText = text
    p._tocLevel = toc_level
    return p


def _draw_back_to_toc(canvas, doc: DocWithTOC):
    """Draw clickable 'Back to Table of Contents' links at top and bottom of each page."""
    text = "Back to Table of Contents"
    canvas.setFont("Helvetica", 9)
    w = canvas.stringWidth(text, "Helvetica", 9)

    # top link
    y_top = letter[1] - 0.55 * inch
    canvas.drawString(doc.leftMargin, y_top, text)
    canvas.linkRect(
        "",
        doc.toc_key,
        (doc.leftMargin, y_top - 2, doc.leftMargin + w, y_top + 10),
        relative=0,
        thickness=0,
    )

    # bottom link
    y_bot = 0.45 * inch
    canvas.drawString(doc.leftMargin, y_bot, text)
    canvas.linkRect(
        "",
        doc.toc_key,
        (doc.leftMargin, y_bot - 2, doc.leftMargin + w, y_bot + 10),
        relative=0,
        thickness=0,
    )


def _tableify(table_data, body_style):
    """Convert table strings into Paragraphs so [[B]] placeholders render as bold."""
    out = []
    for row in table_data:
        out_row = []
        for cell in row:
            # Keep empty cells as empty string to avoid Paragraph issues
            if cell is None:
                cell = ""
            cell_s = str(cell)
            if cell_s.strip():
                out_row.append(Paragraph(_fmt(cell_s), body_style))
            else:
                out_row.append("")
        out.append(out_row)
    return out


def _table_style() -> TableStyle:
    return TableStyle(
        [
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )


def _hr(width: float) -> Table:
    """A simple horizontal rule using a 1-row table."""
    t = Table([[""]], colWidths=[width])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1, colors.grey)]))
    return t


def build_pdf(
    out_path: str,
    title: str,
    journals,  # List[Tuple[journal_title: str, pages: List[PageNode]]]
    selection: Selection,
    include_tables: bool = True,
    divider_pages: bool = True,
):
    """Build a single PDF from multiple journals.

    journals: [(journal_title, pages), ...] in the order they should appear in the PDF.
    selection.items uses (journal_title, page_title, heading_title_or_None) to include content.

    divider_pages:
      - True: insert a dedicated divider page (journal title + rule) between journals
      - False: continuous flow (still inserts a journal heading in TOC/body, but no dedicated page)
    """
    styles = getSampleStyleSheet()
    Title = ParagraphStyle("Title", parent=styles["Title"], spaceAfter=18)
    H1 = ParagraphStyle("H1", parent=styles["Heading1"], spaceBefore=18, spaceAfter=12)
    H2 = ParagraphStyle("H2", parent=styles["Heading2"], spaceBefore=14, spaceAfter=8)
    Body = ParagraphStyle("Body", parent=styles["BodyText"], leading=13, spaceAfter=8)

    wanted = set(selection.items)
    include_whole_page = {(j, p) for (j, p, h) in selection.items if h is None}

    toc_key = _key_for(f"{title}/toc")

    story = []
    story.append(Paragraph(escape(title), Title))
    story.append(PageBreak())

    # TOC (clickable)
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("TOC1", fontSize=11, leftIndent=20, firstLineIndent=-10, spaceAfter=6),
        ParagraphStyle("TOC2", fontSize=10, leftIndent=40, firstLineIndent=-10, spaceAfter=4),
    ]
    toc_heading = _heading("Table of Contents", H1, f"{title}/toc", toc_level=0)
    toc_heading._bookmarkName = toc_key  # ensure back-to-toc links jump correctly
    story.append(toc_heading)
    story.append(toc)
    story.append(PageBreak())

    # Content
    for journal_title, pages in journals:
        # Skip journal if nothing selected from it
        if not any(j == journal_title for (j, _, _) in selection.items):
            continue

        # Always add a journal heading so it shows in TOC and body.
        story.append(_heading(journal_title, H1, f"{title}/journal/{journal_title}", toc_level=0))

        # Make journal boundaries visually obvious.
        content_width = letter[0] - (0.8 * inch) - (0.8 * inch)
        story.append(Spacer(1, 8))
        story.append(_hr(content_width))
        story.append(Spacer(1, 14))
        if divider_pages:
            story.append(PageBreak())

        for page in pages:
            # Is anything selected from this page?
            page_selected = ((journal_title, page.title) in include_whole_page) or any(
                (journal_title, page.title, h.title) in wanted for h in page.headings
            )
            if not page_selected:
                continue

            story.append(_heading(page.title, H1, f"{title}/{journal_title}/page/{page.title}", toc_level=0))

            # Preface blocks only if whole page selected
            if (journal_title, page.title) in include_whole_page:
                for b in page.preface_blocks:
                    if b.kind == "p":
                        story.append(Paragraph(_fmt(b.text), Body))
                    elif b.kind in ("ul", "ol"):
                        bullets = "<br/>".join([f"• {_fmt(line)}" for line in b.text.splitlines() if line.strip()])
                        story.append(Paragraph(bullets, Body))
                    elif b.kind == "table" and include_tables and b.table:
                        tbl = Table(_tableify(b.table, Body), hAlign="LEFT")
                        tbl.setStyle(_table_style())
                        story.append(tbl)
                        story.append(Spacer(1, 8))

            # Headings
            for heading in page.headings:
                if (journal_title, page.title) in include_whole_page or (journal_title, page.title, heading.title) in wanted:
                    story.append(
                        _heading(
                            heading.title,
                            H2,
                            f"{title}/{journal_title}/page/{page.title}/h2/{heading.title}",
                            toc_level=1,
                        )
                    )
                    for b in heading.blocks:
                        if b.kind == "p":
                            story.append(Paragraph(_fmt(b.text), Body))
                        elif b.kind in ("ul", "ol"):
                            bullets = "<br/>".join([f"• {_fmt(line)}" for line in b.text.splitlines() if line.strip()])
                            story.append(Paragraph(bullets, Body))
                        elif b.kind == "table" and include_tables and b.table:
                            tbl = Table(_tableify(b.table, Body), hAlign="LEFT")
                            tbl.setStyle(_table_style())
                            story.append(tbl)
                            story.append(Spacer(1, 8))

            story.append(PageBreak())

    doc = DocWithTOC(
        out_path,
        pagesize=letter,
        leftMargin=0.8 * inch,
        rightMargin=0.8 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.8 * inch,
        title=title,
        toc_key=toc_key,
    )
    doc.multiBuild(
        story,
        maxPasses=6,
        onFirstPage=_draw_back_to_toc,
        onLaterPages=_draw_back_to_toc,
    )
