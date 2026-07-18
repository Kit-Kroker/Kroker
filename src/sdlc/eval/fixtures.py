"""Fixtures for the prompt eval loop: a proposer's frozen input, captured
from a completed run's history.

Pure core here; the live Temporal->events adapter is a documented seam (see
capture_cli in cli.py), mirroring drift.py whose real HistoryProvider ships
unimplemented and fake-tested. A fixture is trivial JSON, so it can also be
hand-authored when a live run is not available.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# Role name is not always the agent name (roles.py). Reverse map, limited to
# the six pure prompt-in/artifact-out proposers.
_ROLE_TO_AGENT = {
    "clarify": "clarify_agent",
    "planner": "planner_agent",
    "qa": "qa_analyst_agent",
    "reviewer": "reviewer_agent",
    "analyst": "analyst_agent",
    "merge_verdict": "merge_verdict_agent",
}
AGENT_TO_ROLE: dict[str, str] = {a: r for r, a in _ROLE_TO_AGENT.items()}
SUPPORTED_ROLES: frozenset[str] = frozenset(_ROLE_TO_AGENT)

# architect + research pass deps to .run(); a prompt-string fixture cannot
# reconstruct a live deps object, so they are refused (spec finding 5).
DEPS_ROLES: frozenset[str] = frozenset({"architect", "research"})

# TemporalModel names its request activity "<agent_name>__model_request"
# (pydantic_ai/durable_exec/temporal/_model.py).
_REQUEST_SUFFIX = "__model_request"


class EvalFixture(BaseModel):
    role: str
    case: str
    prompt: str
    model: str
    source_run_id: str
    captured_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc))


def _role_for_activity(activity: str) -> str | None:
    if not activity.endswith(_REQUEST_SUFFIX):
        return None
    agent = activity[: -len(_REQUEST_SUFFIX)]
    return AGENT_TO_ROLE.get(agent)          # None for deps/unsupported roles


def extract_user_prompt(messages: list[dict[str, Any]]) -> str | None:
    """First UserPromptPart's text from a serialized message list. The initial
    request's user prompt is the frozen input; later requests (tool retries)
    are ignored by taking the first."""
    for msg in messages:
        for part in msg.get("parts", []):
            if part.get("part_kind") == "user-prompt":
                content = part.get("content")
                if isinstance(content, str):
                    return content
                # content can be a list of parts; join the string ones
                if isinstance(content, list):
                    text = "".join(c for c in content if isinstance(c, str))
                    if text:
                        return text
    return None


def fixtures_from_events(run_id: str, case: str, events: list[dict[str, Any]],
                         registry: dict[str, Any]) -> list[EvalFixture]:
    """Pure: normalized history events -> one fixture per supported proposer.

    A normalized event is a dict with "activity" (str) and "input" (dict with
    "messages": list[serialized ModelMessage]). The model is read from the
    registry (a role's declared model), not the event: TemporalModel omits
    model_id from the payload when the default model is used."""
    out: dict[str, EvalFixture] = {}
    for ev in events:
        activity = ev.get("activity")
        if not isinstance(activity, str):
            continue
        role = _role_for_activity(activity)
        if role is None or role in out:          # skip unsupported + keep first
            continue
        cfg = registry.get(role)
        if cfg is None:                          # role not in this registry
            continue
        messages = (ev.get("input") or {}).get("messages")
        if not isinstance(messages, list):
            continue
        prompt = extract_user_prompt(messages)
        if prompt is None:
            continue
        out[role] = EvalFixture(role=role, case=case, prompt=prompt,
                                model=cfg.model, source_run_id=run_id)
    return list(out.values())


def write_fixtures(fixtures: list[EvalFixture], agents_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for fx in fixtures:
        d = agents_dir / fx.role / "fixtures"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{fx.case}.json"
        p.write_text(fx.model_dump_json(indent=2), encoding="utf-8")
        paths.append(p)
    return paths


def load_fixture(path: Path) -> EvalFixture:
    return EvalFixture.model_validate_json(path.read_text(encoding="utf-8"))
