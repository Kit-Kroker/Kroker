"""Injected collaborators and per-request limits for the operator tools.

Everything a verb needs arrives here rather than being imported, so a unit
test substitutes a fake poller and an in-memory BoardStore without a Temporal
client, an HTTP server, or a model.

follow_calls is a STREAK, not a total: note_other_tool() resets it. The brake
the spec asks for is on *consecutive* waits -- an agent that reports to the
operator and then waits again is behaving correctly, and only an agent that
waits forever without reporting is not. reset_request_state() additionally
zeroes it per HTTP request; agent.py installs that as ASGI middleware,
because create_web_app holds one deps object for the life of the mount.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import ToolError


@dataclass
class OperatorDeps:
    poller: Any                 # dashboard.fleet.FleetPoller
    board: Any                  # board.store.BoardStore
    starter: Any                # async (IdeaBrief, PipelineConfig, str) -> str
    actor: str = "chat:unknown"
    max_artifact_bytes: int = 32 * 1024
    max_follow_calls: int = 10
    follow_calls: int = 0

    def reset_request_state(self) -> None:
        self.follow_calls = 0

    def note_follow(self) -> None:
        if self.follow_calls >= self.max_follow_calls:
            raise ToolError(
                f"refusing a {self.follow_calls + 1}th consecutive wait; "
                f"report to the operator before waiting again")
        self.follow_calls += 1

    def note_other_tool(self) -> None:
        self.follow_calls = 0
