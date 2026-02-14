from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple
import json
import re

from bs4 import BeautifulSoup
from bs4.element import Tag


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


# We replace Foundry "link-like" syntaxes with readable placeholders instead of removing them.
# Placeholders are marked as: [[B]][Label][[/B]]
# (pdf_builder.py can render [[B]]...[[/B]] as bold safely)
FOUNDY_PLACEHOLDER_PATTERNS = [
    # @UUID[..]{label}
    (re.compile(r"@UUID\[[^\]]+\]\{([^}]+)\}"), r"[[B]][\1][[/B]]"),
    # @Compendium[..]{label}
    (re.compile(r"@Compendium\[[^\]]+\]\{([^}]+)\}"), r"[[B]][\1][[/B]]"),
    # Generic @Type[..]{label} e.g. @Actor/@Item
    (re.compile(r"@[A-Za-z]+\[[^\]]+\]\{([^}]+)\}"), r"[[B]][\1][[/B]]"),
    # Embed syntaxes (keep readaloud text if present)
    (re.compile(r'@Embed\[[^\]]+readaloud="([^"]+)"\]'), r"\1"),
    # Unlabeled macros -> generic placeholder
    (re.compile(r"@UUID\[[^\]]+\]"), r"[[B]][Linked Content][[/B]]"),
    (re.compile(r"@Compendium\[[^\]]+\]"), r"[[B]][Linked Content][[/B]]"),
    (re.compile(r"@Embed\[[^\]]+\]"), r""),
]


def replace_foundry_links_with_placeholders(html: str) -> str:
    """Convert Foundry link markup into readable placeholders so we don't leave blank gaps."""
    s = html or ""

    # 1) Inline Foundry macro syntax in the raw HTML/text.
    for pat, repl in FOUNDY_PLACEHOLDER_PATTERNS:
        s = pat.sub(repl, s)

    # 2) HTML entity/content links that may not have visible text.
    soup = BeautifulSoup(s, "lxml")

    def label_for(t: Tag) -> str:
        lbl = t.get_text(" ", strip=True) or ""
        if lbl:
            return lbl
        for attr in ("data-name", "data-label", "data-tooltip", "data-tooltip-content", "data-document-name", "aria-label", "title"):
            v = t.get(attr)
            if v:
                v = str(v).strip()
                if v:
                    return v
        # Try to derive something from UUID/pack when no label is present.
        uuid = t.get("data-uuid") or t.get("data-document-uuid") or t.get("data-id") or ""
        pack = t.get("data-pack") or ""
        dtype = t.get("data-type") or t.get("data-document") or ""
        # UUIDs often look like: Actor.abc123 or Compendium.packName.documentId
        if uuid:
            # Take the final segment after '.' as a last resort (better than blank)
            tail = str(uuid).split(".")[-1].strip()
            if tail:
                return tail
        if pack:
            return str(pack).strip()
        if dtype:
            return str(dtype).strip()
        return "Linked Content"

    for t in soup.find_all(["a", "span"]):
        cls = t.get("class") or []
        if "content-link" in cls or "entity-link" in cls:
            lbl = label_for(t)
            t.replace_with(f"[[B]][{lbl}][[/B]]")

    return str(soup)


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
    html = replace_foundry_links_with_placeholders(html)
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
            items = [_clean_text(li.get_text(" ", strip=True)) for li in node.find_all("li")]
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


def parse_journal(path: str) -> tuple[str, List[PageNode]]:
    """
    Returns (journal_title, list_of_pages).
    Works with a JournalEntry export that has pages[] and text.content.
    """
    data = load_journal_json(path)

    # Try a few common places for a title; fall back to filename-ish later in app.py if needed
    journal_title = (data.get("name") or data.get("title") or "").strip() or "Journal"

    pages = data.get("pages", []) or []
    pages = sorted(pages, key=lambda p: p.get("sort", 0))

    out: List[PageNode] = []
    for p in pages:
        title = (p.get("name") or "Untitled").strip()
        html = ((p.get("text") or {}).get("content")) or ""
        preface, headings = parse_page_html_to_structure(html)
        out.append(PageNode(title=title, headings=headings, preface_blocks=preface))

    return journal_title, out
