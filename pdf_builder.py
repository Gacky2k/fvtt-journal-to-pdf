from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple
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


@dataclass
class Selection:
    # List of (page_title, heading_title or None)
    # None = include whole page (preface + all headings)
    items: List[Tuple[str, Optional[str]]]


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
    text = "Back to Table of Contents"
    canvas.setFont("Helvetica", 9)
    w = canvas.stringWidth(text, "Helvetica", 9)

    # top
    y_top = letter[1] - 0.55 * inch
    canvas.drawString(doc.leftMargin, y_top, text)
    canvas.linkRect("", doc.toc_key,
                    (doc.leftMargin, y_top - 2, doc.leftMargin + w, y_top + 10),
                    relative=0, thickness=0)

    # bottom
    y_bot = 0.45 * inch
    canvas.drawString(doc.leftMargin, y_bot, text)
    canvas.linkRect("", doc.toc_key,
                    (doc.leftMargin, y_bot - 2, doc.leftMargin + w, y_bot + 10),
                    relative=0, thickness=0)


def build_pdf(
    out_path: str,
    title: str,
    pages,                 # List[PageNode] from fvtt_parser
    selection: Selection,
    include_tables: bool = True,
):
    styles = getSampleStyleSheet()
    Title = ParagraphStyle("Title", parent=styles["Title"], spaceAfter=18)
    H1 = ParagraphStyle("H1", parent=styles["Heading1"], spaceBefore=18, spaceAfter=12)
    H2 = ParagraphStyle("H2", parent=styles["Heading2"], spaceBefore=14, spaceAfter=8)
    Body = ParagraphStyle("Body", parent=styles["BodyText"], leading=13, spaceAfter=8)

    # Selection lookup
    wanted = set(selection.items)
    include_whole_page = {p for (p, h) in selection.items if h is None}

    toc_key = _key_for(f"{title}/toc")

    story = []
    story.append(Paragraph(escape(title), Title))
    story.append(PageBreak())

    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("TOC1", fontSize=11, leftIndent=20, firstLineIndent=-10, spaceAfter=6),
        ParagraphStyle("TOC2", fontSize=10, leftIndent=40, firstLineIndent=-10, spaceAfter=4),
    ]
    toc_heading = _heading("Table of Contents", H1, f"{title}/toc", toc_level=0)
    toc_heading._bookmarkName = toc_key  # ensure matches for back-links
    story.append(toc_heading)
    story.append(toc)
    story.append(PageBreak())

    # Build body
    for page in pages:
        if page.title not in include_whole_page and all((page.title, h.title) not in wanted for h in page.headings):
            # nothing selected on this page
            continue

        story.append(_heading(page.title, H1, f"{title}/page/{page.title}", toc_level=0))

        # Preface blocks only if whole page selected
        if page.title in include_whole_page:
            for b in page.preface_blocks:
                if b.kind == "p":
                    story.append(Paragraph(escape(b.text), Body))
                elif b.kind in ("ul", "ol"):
                    # simple bullets
                    bullets = "<br/>".join([f"• {escape(line)}" for line in b.text.splitlines() if line.strip()])
                    story.append(Paragraph(bullets, Body))
                elif b.kind == "table" and include_tables and b.table:
                    tbl = Table(b.table, hAlign="LEFT")
                    tbl.setStyle(TableStyle([
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]))
                    story.append(tbl)
                    story.append(Spacer(1, 8))

        for heading in page.headings:
            if page.title in include_whole_page or (page.title, heading.title) in wanted:
                story.append(_heading(heading.title, H2, f"{title}/page/{page.title}/h2/{heading.title}", toc_level=1))
                for b in heading.blocks:
                    if b.kind == "p":
                        story.append(Paragraph(escape(b.text), Body))
                    elif b.kind in ("ul", "ol"):
                        bullets = "<br/>".join([f"• {escape(line)}" for line in b.text.splitlines() if line.strip()])
                        story.append(Paragraph(bullets, Body))
                    elif b.kind == "table" and include_tables and b.table:
                        tbl = Table(b.table, hAlign="LEFT")
                        tbl.setStyle(TableStyle([
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                            ("LEFTPADDING", (0, 0), (-1, -1), 6),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ]))
                        story.append(tbl)
                        story.append(Spacer(1, 8))

        story.append(PageBreak())

    doc = DocWithTOC(
        out_path,
        pagesize=letter,
        leftMargin=0.8 * inch, rightMargin=0.8 * inch,
        topMargin=0.8 * inch, bottomMargin=0.8 * inch,
        title=title,
        toc_key=toc_key,
    )
    doc.multiBuild(
        story,
        maxPasses=6,
        onFirstPage=_draw_back_to_toc,
        onLaterPages=_draw_back_to_toc
    )
