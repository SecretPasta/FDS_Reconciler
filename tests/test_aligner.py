"""Tests for HeadingAligner — deterministic, no real embeddings."""
from __future__ import annotations

import math

import pytest

from app.comparison.aligner import HeadingAligner
from app.config import AlignmentSettings
from app.domain.section import Location, ParsedDoc, Section


# ── fixtures & helpers ────────────────────────────────────────────────────────

_SETTINGS = AlignmentSettings()


def _unit(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in values))
    return [x / norm for x in values] if norm > 0 else values


def _sec(doc_id: str, num: str | None, heading: str) -> Section:
    return Section(
        id=f"{doc_id}::{num or heading[:8]}",
        location=Location(
            filename=f"{doc_id}.pdf",
            heading_number=num,
            heading_path=[heading],
        ),
        heading=heading,
    )


def _doc(doc_id: str, sections: list[Section]) -> ParsedDoc:
    return ParsedDoc(doc_id=doc_id, filename=f"{doc_id}.pdf", sections=sections)


class _MockEmbedder:
    """Returns a pre-defined embedding per heading text. Satisfies EmbedderClient protocol."""

    def __init__(self, emb_map: dict[str, list[float]]) -> None:
        self._map = emb_map

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    async def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError

    async def embed_for_similarity(self, texts: list[str]) -> list[list[float]]:
        return [self._map[t] for t in texts]


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_exact_match() -> None:
    """Identical heading numbers and text → all pairs aligned, nothing left over."""
    s1a = _sec("A", "1.0", "Introduction")
    s2a = _sec("A", "2.0", "Overview")
    s1b = _sec("B", "1.0", "Introduction")
    s2b = _sec("B", "2.0", "Overview")

    embedder = _MockEmbedder({
        "Introduction": _unit([1.0, 0.0, 0.0, 0.0]),
        "Overview":     _unit([0.0, 1.0, 0.0, 0.0]),
    })
    result = await HeadingAligner(embedder, _SETTINGS).align(_doc("A", [s1a, s2a]), _doc("B", [s1b, s2b]))

    assert len(result.aligned_pairs) == 2
    assert result.unmatched_a == []
    assert result.unmatched_b == []
    ids = {(a.id, b.id) for a, b in result.aligned_pairs}
    assert (s1a.id, s1b.id) in ids
    assert (s2a.id, s2b.id) in ids


@pytest.mark.asyncio
async def test_renamed_section() -> None:
    """Same heading number, different heading text → heading_number weight carries the match."""
    s1a = _sec("A", "1.0", "Introduction")
    s2a = _sec("A", "2.0", "System Overview")
    s1b = _sec("B", "1.0", "Introduction")
    s2b = _sec("B", "2.0", "Architecture Overview")  # renamed

    # Architecture Overview is semantically close to System Overview
    emb_sys  = _unit([0.0, 1.0, 0.0, 0.0])
    emb_arch = _unit([0.0, 0.9, 0.1, 0.0])   # high cosine with emb_sys

    embedder = _MockEmbedder({
        "Introduction":        _unit([1.0, 0.0, 0.0, 0.0]),
        "System Overview":     emb_sys,
        "Architecture Overview": emb_arch,
    })
    result = await HeadingAligner(embedder, _SETTINGS).align(_doc("A", [s1a, s2a]), _doc("B", [s1b, s2b]))

    assert len(result.aligned_pairs) == 2
    assert result.unmatched_a == []
    assert result.unmatched_b == []


@pytest.mark.asyncio
async def test_missing_section() -> None:
    """Section present in A but absent from B → lands in unmatched_a."""
    s1a = _sec("A", "1.0", "Introduction")
    s2a = _sec("A", "2.0", "Overview")       # only in A
    s3a = _sec("A", "3.0", "Details")
    s1b = _sec("B", "1.0", "Introduction")
    s3b = _sec("B", "3.0", "Details")

    embedder = _MockEmbedder({
        "Introduction": _unit([1.0, 0.0, 0.0, 0.0]),
        "Overview":     _unit([0.0, 1.0, 0.0, 0.0]),
        "Details":      _unit([0.0, 0.0, 1.0, 0.0]),
    })
    result = await HeadingAligner(embedder, _SETTINGS).align(
        _doc("A", [s1a, s2a, s3a]),
        _doc("B", [s1b, s3b]),
    )

    assert len(result.aligned_pairs) == 2
    assert len(result.unmatched_a) == 1
    assert result.unmatched_a[0].id == s2a.id
    assert result.unmatched_b == []