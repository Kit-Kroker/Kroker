"""FR-020(b)+(c) (T030): the two added activity wirings are unreachable.

(b) `..__toolset__<agent>__validate_args` is REGISTERED for every agent but
is scheduled only for `args_validator`/`DynamicToolset`-shaped toolsets and
explicit `validate_tool_arguments` calls — none of which exist in Kroker
source. (c) `..__model_cancel_suspended_response` is likewise registered
(wire shape exists) but is scheduled only when a SUSPENDED (deferred or
streamed) response is cancelled, and Kroker never streams.

Fast tier, no server: this is a static proof. The REACHABILITY half is the
scan (zero call sites); the WIRE half is the registered-name assertion. A
failure here escalates: it means a shipped path grew a scheduling route.
"""

from pathlib import Path

from pydantic_ai.durable_exec.temporal import TemporalDurability

from sdlc.agents.roles import ALL_TEMPORAL_AGENTS

# tests/durability/ -> repo root, two levels up.
_ROOT = Path(__file__).resolve().parents[2]

# The only pydantic-ai 2.51 paths that SCHEDULE validate_args, plus the
# streaming paths that alone can suspend (and so cancel) a model response.
# All of them are absent from Kroker source; if one appears, the matching
# activity becomes reachable and this file's premise is void.
_SCHEDULE_PATHS = (
    "args_validator",
    "DynamicToolset",
    "validate_tool_arguments",
    "cancel_suspended_response",
    "run_stream(",
    "model_request_stream",
    "event_stream_handler",
)


def _offenders(needle: str) -> list[str]:
    hits: list[str] = []
    for base in (_ROOT / "src", _ROOT / "agents"):
        for f in sorted(base.rglob("*.py")):
            for lineno, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if needle in line:
                    hits.append(f"{f.relative_to(_ROOT)}:{lineno}")
    return hits


def test_no_streaming_or_args_validation_call_sites_in_source():
    """Zero occurrences of every validate_args/streaming scheduling path in
    src/ and agents/: no shipped code can put the toolset validate_args or
    the cancel-suspended activity on the wire (FR-020b scan half)."""
    for needle in _SCHEDULE_PATHS:
        assert not _offenders(needle), (
            f"{needle!r} appeared in Kroker source; the corresponding "
            f"durability activity is now reachable — escalate (FR-020b/c)"
        )


def test_cancel_suspended_response_is_registered_but_unreachable():
    """Every shipped agent registers `..__model_cancel_suspended_response`
    (the wire shape exists, FR-020c), while the scan above proves nothing
    can schedule it: Kroker runs non-streaming `agent.run` only. Residual
    recorded per R4c — the arity difference is unreachable by construction."""
    for agent in ALL_TEMPORAL_AGENTS:
        bound = TemporalDurability.from_agent(agent)
        assert bound is not None, f"{agent.name} lost its durability capability"
        names = {
            defn.name
            for fn in bound.temporal_activities
            if (defn := getattr(fn, "__temporal_activity_definition", None)) is not None
        }
        assert any(n.endswith("__model_cancel_suspended_response") for n in names), (
            f"{agent.name} does not register model_cancel_suspended_response"
        )
