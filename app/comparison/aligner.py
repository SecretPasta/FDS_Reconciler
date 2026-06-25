from __future__ import annotations

import math
from dataclasses import dataclass

from Levenshtein import ratio as lev_ratio

from app.config import AlignmentSettings
from app.domain.section import ParsedDoc, Section
from app.ports.embedder import EmbedderClient


@dataclass
class AlignmentResult:
    aligned_pairs: list[tuple[Section, Section]]
    unmatched_a: list[Section]
    unmatched_b: list[Section]


class HeadingAligner:
    def __init__(self, embedder: EmbedderClient, settings: AlignmentSettings) -> None:
        self._embedder = embedder
        self._settings = settings

    async def align(self, doc_a: ParsedDoc, doc_b: ParsedDoc) -> AlignmentResult:
        secs_a = doc_a.sections
        secs_b = doc_b.sections

        if not secs_a or not secs_b:
            return AlignmentResult(
                aligned_pairs=[],
                unmatched_a=list(secs_a),
                unmatched_b=list(secs_b),
            )

        # Batch-embed all headings in one call
        texts = [s.heading for s in secs_a] + [s.heading for s in secs_b]
        all_embs = await self._embedder.embed_for_similarity(texts)
        embs_a = all_embs[: len(secs_a)]
        embs_b = all_embs[len(secs_a) :]

        # Score every (A, B) candidate pair
        scored: list[tuple[float, int, int]] = [
            (_score(secs_a[i], secs_b[j], embs_a[i], embs_b[j], self._settings), i, j)
            for i in range(len(secs_a))
            for j in range(len(secs_b))
        ]

        # Greedy bipartite match — sort descending, commit first uncontested pair ≥ threshold
        scored.sort(reverse=True)
        matched_a: set[int] = set()
        matched_b: set[int] = set()
        aligned: list[tuple[Section, Section]] = []

        for score, i, j in scored:
            if score < self._settings.threshold:
                break
            if i in matched_a or j in matched_b:
                continue
            aligned.append((secs_a[i], secs_b[j]))
            matched_a.add(i)
            matched_b.add(j)

        return AlignmentResult(
            aligned_pairs=aligned,
            unmatched_a=[s for i, s in enumerate(secs_a) if i not in matched_a],
            unmatched_b=[s for j, s in enumerate(secs_b) if j not in matched_b],
        )


# ── scoring ───────────────────────────────────────────────────────────────────

def _score(
    sa: Section,
    sb: Section,
    emb_a: list[float],
    emb_b: list[float],
    s: AlignmentSettings,
) -> float:
    cos = _cosine(emb_a, emb_b)
    lev = lev_ratio(sa.heading.lower(), sb.heading.lower())

    num_a = sa.location.heading_number
    num_b = sb.location.heading_number

    if num_a and num_b:
        num_sim = lev_ratio(num_a, num_b)
        return s.w_heading_num * num_sim + s.w_heading_embed * cos + s.w_levenshtein * lev

    # Reweight when heading numbers are absent on either side
    return 0.75 * cos + 0.25 * lev


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)