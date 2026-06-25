from __future__ import annotations

from app.domain.comparison import ComparisonResult, DiffEntry, MatchEntry, MissingEntry
from app.domain.section import Section
from app.domain.verdict import MissingExplanationBatch, PairwiseVerdict


def assemble(
    aligned_pairs: list[tuple[Section, Section]],
    verdicts: dict[str, PairwiseVerdict],  # keyed by section_a.id
    unmatched_a: list[Section],
    unmatched_b: list[Section],
    missing_explanations: MissingExplanationBatch,
) -> ComparisonResult:
    """Pure assembly — no I/O. Keys verdicts by section_a.id."""
    match_list: list[MatchEntry] = []
    diff_list: list[DiffEntry] = []

    for sec_a, sec_b in aligned_pairs:
        verdict = verdicts.get(sec_a.id)
        if verdict is None:
            continue

        src_a = verdict.source_a or sec_a.location.cite()
        src_b = verdict.source_b or sec_b.location.cite()

        if verdict.verdict == "MATCH":
            match_list.append(MatchEntry(
                textA=verdict.doc_a_text or sec_a.body_text,
                textB=verdict.doc_b_text or sec_b.body_text,
                source=f"{src_a} + {src_b}",
            ))
        else:
            diff_list.append(DiffEntry(
                docA_text=verdict.doc_a_text or sec_a.body_text,
                docB_text=verdict.doc_b_text or sec_b.body_text,
                reason=verdict.reason or "",
                sourceA=src_a,
                sourceB=src_b,
            ))

    # Index explanations by cite string so missing sections can look them up
    expl_by_cite: dict[str, str] = {
        e.location: e.explanation for e in missing_explanations.entries
    }

    missing_list: list[MissingEntry] = []

    for sec in unmatched_a:
        cite = sec.location.cite()
        missing_list.append(MissingEntry(
            text=sec.body_text.strip() or sec.heading,
            source_file=sec.location.filename,
            location=cite,
            explanation=expl_by_cite.get(cite, "Section present in V0 but absent from V5."),
        ))

    for sec in unmatched_b:
        cite = sec.location.cite()
        missing_list.append(MissingEntry(
            text=sec.body_text.strip() or sec.heading,
            source_file=sec.location.filename,
            location=cite,
            explanation=expl_by_cite.get(cite, "Section present in V5 but absent from V0."),
        ))

    return ComparisonResult(missing=missing_list, diff=diff_list, match=match_list)