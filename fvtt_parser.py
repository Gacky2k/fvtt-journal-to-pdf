from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple
import json
import re

from bs4 import BeautifulSoup


@dataclass
class ContentBlock:
    kind: str  # "p", "h2", "h3", "table", "ul", "ol"
    text: str
    table: Optional[List[List[str]]] = None


@dataclass
class HeadingNode:
    title: str
    level: int  # 2/3/4 etc
    blocks: List[ContentBlock]


@dataclass
class PageNode:
    title: str
    headings: List[HeadingNode]
    # Any content before first heading
    preface_blocks: List[ContentBlock]


FOUNDY_CRUFT_PATTERNS = [
    # @UUID[...] and @UUID[..]{label}
    (re.compile(r"@UUID\[[^\]]+\]\{([^}]+)\}"), r"\1"),
    (re.compile(r"@UUID\[[^\]]+\]"), r""),
    # Embed syntaxes (keep readaloud text if present)
    (re.compile(r"@Embed\[[^\]]+readaloud=\"([^\"]+)\"\]"), r"\1"),
    (re.compile(r"@Embed\[[^\]]+\]"), r""),
]


def strip_foundry_macros(html: str) -> str:
    s = html or ""
    for pat, repl in FOUNDY_CRUFT_PATTERNS:
        s = pat.sub(repl, s)
    return s


def load_journal_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_table(el) -> List[List[str]]:
    rows: List[List[str]] = []
    for tr in el.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        row = [" ".join(c.get_text(" ", strip=True).split()) for c in cells]
        if any(cell for cell in row):
            rows.append(row)
    return rows


def _clean_text(s: str) -> str:
    return " ".join((s or "").split())


def parse_page_html_to_structure(html: str) -> Tuple[List[ContentBlock], List[HeadingNode]]:
    """
    Splits content into:
      - preface blocks (before first heading)
      - headings with their following blocks until next heading
    """
    html = strip_foundry_macros(html)
    soup = BeautifulSoup(html, "lxml")

    # Remove images/figures (optional)
    for tag in soup.find_all(["img", "figure"]):
        tag.decompose()

    # We'll iterate through body children in document order
    body = soup.body or soup
    preface: List[ContentBlock] = []
    headings: List[HeadingNode] = []

    current_heading: Optional[HeadingNode] = None

    def add_block(block: ContentBlock):
        nonlocal current_heading
        if current_heading is None:
            preface.append(block)
        else:
            current_heading.blocks.append(block)

    for node in body.descendants:
        if getattr(node, "name", None) is None:
            continue

        name = node.name.lower()

        # Headings
        if name in ("h2", "h3", "h4"):
            title = _clean_text(node.get_text(" ", strip=True))
            level = int(name[1])
            current_heading = HeadingNode(title=title, level=level, blocks=[])
            headings.append(current_heading)
            continue

        # Paragraph-ish blocks
        if name == "p":
            text = _clean_text(node.get_text(" ", strip=True))
            if text:
                add_block(ContentBlock(kind="p", text=text))
            continue

        # Lists
        if name in ("ul", "ol"):
            items = [ _clean_text(li.get_text(" ", strip=True)) for li in node.find_all("li") ]
            items = [i for i in items if i]
            if items:
                add_block(ContentBlock(kind=name, text="\n".join(items)))
            continue

        # Tables
        if name == "table":
            table = _parse_table(node)
            if table:
                add_block(ContentBlock(kind="table", text="", table=table))
            continue

    return preface, headings


def parse_journal(path: str) -> List[PageNode]:
    """
    Returns list of pages with headings/blocks.
    Works with a JournalEntry export that has pages[] and text.content.
    """
    data = load_journal_json(path)
    pages = data.get("pages", []) or []
    # stable ordering
    pages = sorted(pages, key=lambda p: p.get("sort", 0))

    out: List[PageNode] = []
    for p in pages:
        title = (p.get("name") or "Untitled").strip()
        html = ((p.get("text") or {}).get("content")) or ""
        preface, headings = parse_page_html_to_structure(html)
        out.append(PageNode(title=title, headings=headings, preface_blocks=preface))
    return out
