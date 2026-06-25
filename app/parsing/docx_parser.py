from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional, Tuple, Union

from docx import Document as open_docx
from docx.document import Document
from docx.oxml.ns import qn
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph as DocxParagraph

from app.domain.section import Location, ParsedDoc, Section, TableData

_HEADING_NUM_RE = re.compile(r'^(\d+(?:\.\d+)*)\.?\s+(.+)', re.DOTALL)
_HEADING_STYLE_RE = re.compile(r'^Heading\s+(\d+)$', re.IGNORECASE)
_w_p = qn('w:p')
_w_tbl = qn('w:tbl')


# ── public entry point ────────────────────────────────────────────────────────

def parse_docx(path: Path, doc_id: str) -> ParsedDoc:
    doc = open_docx(str(path))
    sections = _extract_sections(doc, path, doc_id)
    return ParsedDoc(doc_id=doc_id, filename=path.name, sections=sections)


# ── section extraction ────────────────────────────────────────────────────────

@dataclass
class _Acc:
    heading: str
    heading_num: str | None
    heading_path: list[str]
    idx: int
    body_lines: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    tables: list[TableData] = field(default_factory=list)

    def to_section(self, doc_id: str, filename: str) -> Section:
        section_id = (
            f"{doc_id}::{self.heading_num}"
            if self.heading_num
            else f"{doc_id}::{self.idx}-{_slugify(self.heading)}"
        )
        return Section(
            id=section_id,
            location=Location(
                filename=filename,
                page_number=None,
                heading_number=self.heading_num,
                heading_path=list(self.heading_path),
            ),
            heading=self.heading,
            body_text="\n".join(self.body_lines).strip(),
            tables=list(self.tables),
            bullets=list(self.bullets),
        )


def _extract_sections(doc: Document, path: Path, doc_id: str) -> list[Section]:
    sections: list[Section] = []
    stack: list[tuple[int, str]] = []  # (depth, full_heading_text)
    acc: _Acc | None = None
    idx = 0

    for element in _iter_body(doc):
        if isinstance(element, DocxParagraph):
            text = element.text.strip()
            if not text:
                continue

            level = _heading_level(element)
            if level is not None:
                if acc is not None:
                    sections.append(acc.to_section(doc_id, path.name))
                heading_num, heading_clean = _parse_heading_num(text)
                stack = [(d, t) for d, t in stack if d < level]
                stack.append((level, text))
                acc = _Acc(
                    heading=heading_clean,
                    heading_num=heading_num,
                    heading_path=[t for _, t in stack],
                    idx=idx,
                )
                idx += 1
            elif acc is not None:
                if _is_bullet(element):
                    acc.bullets.append(text)
                else:
                    acc.body_lines.append(text)

        elif isinstance(element, DocxTable) and acc is not None:
            acc.tables.append(_table_data(element))

    if acc is not None:
        sections.append(acc.to_section(doc_id, path.name))

    return sections


# ── helpers ───────────────────────────────────────────────────────────────────

def _iter_body(doc: Document) -> Iterator[Union[DocxParagraph, DocxTable]]:
    for child in doc.element.body:
        if child.tag == _w_p:
            yield DocxParagraph(child, doc)  # type: ignore[arg-type]
        elif child.tag == _w_tbl:
            yield DocxTable(child, doc)  # type: ignore[arg-type]


def _heading_level(para: DocxParagraph) -> Optional[int]:
    style = para.style
    if style is None:
        return None
    m = _HEADING_STYLE_RE.match(style.name)
    return int(m.group(1)) if m else None


def _is_bullet(para: DocxParagraph) -> bool:
    style = para.style
    if style is None:
        return False
    style_lower = style.name.lower()
    return (
        "list bullet" in style_lower
        or "list number" in style_lower
        or "list paragraph" in style_lower
    )


def _table_data(table: DocxTable) -> TableData:
    raw = [[cell.text.strip() for cell in row.cells] for row in table.rows]
    if not raw:
        return TableData(headers=[], rows=[])
    return TableData(headers=raw[0], rows=raw[1:])


def _parse_heading_num(text: str) -> Tuple[Optional[str], str]:
    m = _HEADING_NUM_RE.match(text)
    if m:
        return m.group(1), m.group(2).strip()
    return None, text


def _slugify(text: str) -> str:
    return re.sub(r'\W+', '-', text.lower()).strip('-')[:40]