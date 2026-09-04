"""The StageContext seam (spec A §3.2).

A step never receives the workflow instance. It receives StageServices: a
frozen record of exactly the eleven capabilities the orchestrator offers,
built once in FeatureWorkflow.__init__ from its own bound methods. B0 §1.1
rejects passing `self` because that exposes everything; this makes "a stage
does not reach into the workflow class" true at runtime rather than by
convention, and it lets a step be unit-tested by handing it stubs, with no
workflow and no Temporal environment at all.

Data travels in the step signature; only capabilities live here. The review
question for any proposed addition is "is this a capability the orchestrator
provides, or a value it holds?" — board publishing was the first thing to
fail that test (spec §3.4).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class StageContext(Protocol):
    """The eleven services, in B0's five groups."""

    # Reporting
    def emit(self, kind: Any, stage: str | None = None, **data: str) -> None: ...
    def stage(self, status: str, trace: str | None = None) -> None: ...

    # Role execution and memoization
    def run_role(
        self, cfg: Any, role: str, model: str, agent: Any, *args: Any, **kwargs: Any
    ) -> Awaitable[Any]: ...
    def cached_stage(
        self,
        cfg: Any,
        stage: str,
        input_json: str,
        output_type: type,
        run_fn: Callable[[], Awaitable[Any]],
        *,
        prompt_digest: str = "",
    ) -> Awaitable[tuple[Any, bool]]: ...
    def revisable_stage(
        self, name: str, cfg: Any, run_fn: Callable[[str | None], Awaitable[Any]]
    ) -> Awaitable[tuple[Any, Any]]: ...

    # Benchmark and memory
    def record(self, cfg: Any, record: Any) -> Awaitable[None]: ...
    def judge(
        self, cfg: Any, artifact_json: str, stage: str, author_model: str
    ) -> Awaitable[Any]: ...
    def recall(
        self, cfg: Any, bank: str, query: str, filters: dict[str, str]
    ) -> Awaitable[Any]: ...
    def retain(
        self, cfg: Any, kind: Any, bank: str, text: str, metadata: dict[str, str]
    ) -> Awaitable[None]: ...

    # Human decisions
    def gate(self, name: str, settings: Any, **kwargs: Any) -> Awaitable[Any]: ...

    # Human questions
    def ask_and_wait(
        self, questions: Sequence[Any], *, stage: str, timeout_hours: int
    ) -> Awaitable[dict[str, str]]: ...


@dataclass(frozen=True, slots=True)
class StageServices:
    """The Protocol's only production implementation. Constructed once, in
    FeatureWorkflow.__init__, from bound methods — never lazily inside a step,
    where a conditional construction could diverge on replay."""

    emit: Callable[..., None]
    stage: Callable[..., None]
    run_role: Callable[..., Awaitable[Any]]
    cached_stage: Callable[..., Awaitable[tuple[Any, bool]]]
    revisable_stage: Callable[..., Awaitable[tuple[Any, Any]]]
    record: Callable[..., Awaitable[None]]
    judge: Callable[..., Awaitable[Any]]
    recall: Callable[..., Awaitable[Any]]
    retain: Callable[..., Awaitable[None]]
    gate: Callable[..., Awaitable[Any]]
    ask_and_wait: Callable[..., Awaitable[dict[str, str]]]
