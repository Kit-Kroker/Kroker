"""QuestionHost -- human clarification question/answer lifecycle (spec A §3.1).

A mixin, following GateHost (workflows/gates.py:54).

Consumes: ReportHost._emit, ReportHost._stage via the MRO.
Owns: _question_answers, _pending_questions.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ..models import OpenQuestion
    from ..observability.trace import RunEventKind
    from ..pending import clarify_pending


class QuestionHost:
    """Mixin. Open questions to a human and block until answered (FR-30x).

    Owns _question_answers and _pending_questions. A stage never touches
    them: it calls ask_and_wait and receives a dict.
    """

    def __init__(self) -> None:
        super().__init__()
        self._question_answers: dict[str, str] = {}
        self._pending_questions: list[str] = []

    @workflow.signal
    def answer_question(self, question_id: str, answer: str) -> None:
        self._question_answers.setdefault(question_id, answer)
        pending = getattr(self, "_pending", None)
        if pending is not None:
            pending.pop(question_id, None)

    async def ask_and_wait(
        self,
        questions: Sequence[OpenQuestion],
        *,
        stage: str = "clarify",
        timeout_hours: int = 72,
    ) -> dict[str, str]:
        """Emit CLARIFICATION_ASKED per question, set the run status, register
        the pending questions, then block on workflow.wait_condition until
        every id has an answer or the deadline passes. Assembled from the
        block currently inline in the clarify body around feature.py:2845-2887
        -- move it verbatim, changing only `self._status = ...` to
        `self._stage(...)` and reading the questions from the parameter
        instead of from `reqs.open_questions`.
        """
        if not questions:
            return {}
        for q in questions:
            self._emit(  # type: ignore[attr-defined]
                RunEventKind.CLARIFICATION_ASKED,
                stage=stage,
                question_id=q.id,
                question=q.question,
                # data is dict[str, str] -- "" not None, or the
                # RunEvent fails validation on the flag-off path.
                dimension=q.dimension.value if q.dimension else "",
            )
        self._stage(f"awaiting:{stage}", trace=stage)  # type: ignore[attr-defined]
        self._pending_questions = [q.id for q in questions]
        pending = getattr(self, "_pending", None)
        if pending is not None:
            for p in clarify_pending(list(questions), set(), opened_at=workflow.now()):
                pending[p.key] = p
        await workflow.wait_condition(
            lambda: all(q.id in self._question_answers for q in questions),
            timeout=timedelta(hours=timeout_hours),
        )
        answers: dict[str, str] = {}
        for q in questions:
            ans = self._question_answers.get(q.id)
            if ans is not None:
                answers[q.id] = ans
            if pending is not None:
                pending.pop(q.id, None)
        for q in questions:
            ans = answers.get(q.id)
            answered = (
                "human"
                if q.id in self._question_answers
                else "suggested"
                if ans is not None
                else "unanswered"
            )
            self._emit(  # type: ignore[attr-defined]
                RunEventKind.CLARIFICATION_ANSWERED,
                stage=stage,
                question_id=q.id,
                answered_by=answered,
            )
        self._pending_questions.clear()
        return answers
