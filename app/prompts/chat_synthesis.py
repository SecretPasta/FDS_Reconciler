from __future__ import annotations

from app.chat.retriever import RetrievedChunk

_BINARY_RULE = """\
This is a strict binary choice — never mix the two branches:

  BRANCH A — context contains relevant information (even partial):
    • Set insufficient_context = false.
    • Provide a substantive answer grounded in the context.
    • Cite every factual claim inline: [filename · §section · page N].
    • Populate the citations list with plain strings in the exact format
      "filename · §section · page N" (omit " · page N" if page is unknown).

    Example output:
      answer: "The three processing stages are intake, validation, and output.
               [doc.pdf · §3.1 · page 4]"
      citations: ["doc.pdf · §3.1 · page 4"]
      insufficient_context: false

  BRANCH B — context does NOT contain information to answer the question:
    • Set insufficient_context = true.
    • Write a brief refusal: "I couldn't find this in the document."
    • Leave the citations list empty.
    • Do NOT speculate, summarise unrelated content, or give a partial answer.

    Example output:
      answer: "I couldn't find information about that topic in the document."
      citations: []
      insufficient_context: true

Never set insufficient_context = true while also providing a substantive answer
or populating citations."""

_SINGLE_DOC_INSTRUCTIONS = (
    "Answer ONLY from the provided context. Do not use prior knowledge.\n\n"
    + _BINARY_RULE
)

_CROSS_DOC_INSTRUCTIONS = (
    "Answer ONLY from the provided context. Do not use prior knowledge.\n"
    "When answering comparative questions, attribute each claim to its source "
    "document (V0 or V5) so the distinction is clear.\n\n"
    + _BINARY_RULE
)


def build_single_doc_prompt(query: str, chunks: list[RetrievedChunk]) -> str:
    return (
        f"## Context\n\n{_format_chunks(chunks)}\n\n"
        f"## Instructions\n{_SINGLE_DOC_INSTRUCTIONS}\n\n"
        f"## Question\n{query}"
    )


def build_cross_doc_prompt(
    query: str,
    chunks_by_doc: dict[str, list[RetrievedChunk]],
) -> str:
    blocks: list[str] = []
    for doc_id, chunks in chunks_by_doc.items():
        label = _doc_label(doc_id, chunks)
        blocks.append(f"## From {label}\n\n{_format_chunks(chunks)}")

    context = "\n\n".join(blocks)
    return (
        f"{context}\n\n"
        f"## Instructions\n{_CROSS_DOC_INSTRUCTIONS}\n\n"
        f"## Question\n{query}"
    )


# ── helpers ───────────────────────────────────────────────────────────────────

def _doc_label(doc_id: str, chunks: list[RetrievedChunk]) -> str:
    """Derive a human-readable label from doc_id or chunk metadata filename."""
    if chunks:
        fname: str = chunks[0].metadata.get("filename", "")
        if fname.lower().endswith(".pdf"):
            return "V0 (PDF)"
        if fname.lower().endswith(".docx"):
            return "V5 (DOCX)"
    return f"doc {doc_id}"


def _format_chunks(chunks: list[RetrievedChunk]) -> str:
    return "\n\n".join(
        f"[{_cite(c.metadata)}]\n{c.display_text}" for c in chunks
    )


def _cite(meta: dict) -> str:
    parts: list[str] = [meta.get("filename", "unknown")]
    section = meta.get("heading_number") or (
        meta["heading_path"][-1] if meta.get("heading_path") else ""
    )
    if section:
        parts.append(f"§{section}")
    if (page := meta.get("page_number")) is not None:
        parts.append(f"page {page}")
    return " · ".join(parts)
