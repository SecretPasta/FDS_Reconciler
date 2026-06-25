from __future__ import annotations

import tiktoken

from app.config import ChunkingSettings
from app.domain.chunk import Chunk, ChunkType
from app.domain.section import Section

_enc = tiktoken.get_encoding("cl100k_base")


def chunk_section(section: Section, settings: ChunkingSettings) -> list[Chunk]:
    doc_id = section.id.split("::")[0]
    breadcrumb = " > ".join(section.location.heading_path)
    seq = 0
    chunks: list[Chunk] = []

    for table in section.tables:
        display = table.to_markdown()
        chunks.append(_make(section, doc_id, "table", _bc(breadcrumb, display), display, seq))
        seq += 1

    if section.body_text.strip():
        paras = [p.strip() for p in section.body_text.splitlines() if p.strip()]
        new_chunks, seq = _pack(paras, "\n", "prose", section, doc_id, breadcrumb, seq, settings)
        chunks.extend(new_chunks)

    if section.bullets:
        bullet_texts = [f"• {b}" for b in section.bullets]
        new_chunks, seq = _pack(bullet_texts, "\n", "bullets", section, doc_id, breadcrumb, seq, settings)
        chunks.extend(new_chunks)

    return chunks


# ── packing ───────────────────────────────────────────────────────────────────

def _pack(
    texts: list[str],
    sep: str,
    chunk_type: ChunkType,
    section: Section,
    doc_id: str,
    breadcrumb: str,
    seq: int,
    settings: ChunkingSettings,
) -> tuple[list[Chunk], int]:
    if not texts:
        return [], seq

    # Fits in a single chunk
    if _tok(sep.join(texts)) <= settings.max_tokens:
        display = sep.join(texts)
        return [_make(section, doc_id, chunk_type, _bc(breadcrumb, display), display, seq)], seq + 1

    chunks: list[Chunk] = []
    buf: list[str] = []
    buf_t = 0
    new_since_flush = False

    def flush() -> None:
        nonlocal seq, buf, buf_t, new_since_flush
        if not buf:
            return
        body = sep.join(buf)
        chunks.append(_make(section, doc_id, chunk_type, _bc(breadcrumb, body), body, seq))
        seq += 1
        # Seed next chunk with trailing overlap window
        ov: list[str] = []
        ov_t = 0
        for p in reversed(buf):
            p_tok = _tok(p)
            if ov_t + p_tok <= settings.overlap_tokens:
                ov.insert(0, p)
                ov_t += p_tok
            else:
                break
        buf, buf_t = ov, ov_t
        new_since_flush = False

    for piece in texts:
        piece_t = _tok(piece)

        # Single piece larger than max: flush pending, emit alone, clear overlap
        if piece_t > settings.max_tokens:
            flush()
            chunks.append(_make(section, doc_id, chunk_type, _bc(breadcrumb, piece), piece, seq))
            seq += 1
            buf, buf_t = [], 0
            new_since_flush = False
            continue

        if buf_t + piece_t > settings.target_tokens:
            flush()

        buf.append(piece)
        buf_t += piece_t
        new_since_flush = True

    # Final flush — only if the buffer contains content added after the last flush
    if new_since_flush or (not chunks and buf):
        display = sep.join(buf)
        chunks.append(_make(section, doc_id, chunk_type, _bc(breadcrumb, display), display, seq))
        seq += 1

    return chunks, seq


# ── helpers ───────────────────────────────────────────────────────────────────

def _tok(text: str) -> int:
    return len(_enc.encode(text))


def _bc(breadcrumb: str, body: str) -> str:
    return f"{breadcrumb}\n\n{body}" if breadcrumb else body


def _make(
    section: Section,
    doc_id: str,
    chunk_type: ChunkType,
    text: str,
    display_text: str,
    seq: int,
) -> Chunk:
    return Chunk(
        id=f"{section.id}::chunk-{seq}",
        section_id=section.id,
        doc_id=doc_id,
        chunk_type=chunk_type,
        text=text,
        display_text=display_text,
        location=section.location,
    )