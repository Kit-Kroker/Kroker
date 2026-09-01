"""Deterministic merge of per-sub-question briefs into one ResearchBrief.

Pure: no model, no network, no filesystem. Everything here is checkable by a
reader, which is the point -- the model's judgment is confined to summary,
confidence, and cross-cutting contradictions (research/stage.py's
synthesize_brief), and it may never author a grounded finding.
"""

from __future__ import annotations

from ..models import (
    ConsultedSource,
    Contradiction,
    Gap,
    GroundedFinding,
    InferredFinding,
    ResearchBrief,
    SubQuestion,
    SubQuestionFinding,
)


def merge_briefs(findings: list[SubQuestionFinding]) -> ResearchBrief:
    """Assemble N partial briefs. Fills every field except `summary`,
    `confidence`, and cross-cutting contradictions -- those need judgment over
    the whole and are written by the synthesis model.

    `brief_ref` is left None; the artifact is stored after synthesis."""
    sub_questions: list[SubQuestion] = []
    sources: list[ConsultedSource] = []
    seen_urls: set[str] = set()
    grounded: list[GroundedFinding] = []
    seen_triples: set[tuple[str, str, str]] = set()
    inferred: list[InferredFinding] = []
    contradictions: list[Contradiction] = []
    gaps: list[Gap] = []

    for f in findings:
        sub_questions.append(f.sub_question)

        if f.failed:
            # A permanently failed sub-question is not silence: it becomes a
            # gap so a short brief is EXPLAINED rather than merely short.
            gaps.append(
                Gap(
                    sub_question_id=f.sub_question.id,
                    what_is_missing=f.sub_question.question,
                    why_it_matters=f"this sub-question did not complete: {f.error}",
                )
            )
            continue

        for s in f.brief.sources_consulted:
            # First-seen wins. Two sub-questions rarely assess the same source
            # differently, and picking a winner by rule beats asking a model.
            if s.url not in seen_urls:
                seen_urls.add(s.url)
                sources.append(s)

        for g in f.brief.grounded_findings:
            # Dedupe ONLY exact triples. The same claim from a DIFFERENT source
            # is corroboration -- the most valuable thing fan-out produces --
            # and collapsing it would destroy the signal. Exact duplicates must
            # go, because brief_digest hashes (source_url, claim) as a list.
            key = (g.source_url, g.quote, g.claim)
            if key not in seen_triples:
                seen_triples.add(key)
                grounded.append(g)

        inferred.extend(f.brief.inferred_findings)
        contradictions.extend(f.brief.contradictions)
        gaps.extend(f.brief.gaps)

    return ResearchBrief(
        sub_questions=sub_questions,
        sources_consulted=sources,
        grounded_findings=grounded,
        inferred_findings=inferred,
        contradictions=contradictions,
        gaps=gaps,
    )
