"""Typed, model-actionable tool failures (E-86 spec 5.3, 11).

A traceback rendered into a chat UI leaks filesystem paths into a transcript
the model then echoes. Every failure a tool can produce therefore leaves this
module as a ToolError whose message is safe to show and specific enough for
the model to do something different next time.
"""

from __future__ import annotations

import functools

from ..board.store import ConflictError, InvalidTransition, NotFoundError
from ..channels.transport import Ambiguous, NoMatch


class ToolError(Exception):
    """A failure the model is expected to read and act on."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def translate(exc: Exception, *, hint: str = "") -> ToolError:
    """Map a known domain exception to a ToolError. Never raises."""
    if isinstance(exc, ToolError):
        return exc
    if isinstance(exc, NoMatch):
        msg = (
            f"{exc.message}\nThis key is no longer pending; re-read the "
            f"inbox or the run and use a current key."
        )
    elif isinstance(exc, Ambiguous):
        msg = f"{exc.message}\nNarrow it by passing an exact key."
    elif isinstance(exc, NotFoundError):
        msg = str(exc)
    elif isinstance(exc, ConflictError):
        msg = f"board conflict: {exc}"
    elif isinstance(exc, InvalidTransition):
        msg = f"invalid board transition: {exc}"
    else:
        # Deliberately type-only: the message may carry paths or credentials.
        msg = f"the factory raised {type(exc).__name__}; the operator should check the server log"
    if hint:
        msg = f"{msg}\n{hint}"
    return ToolError(msg)


def guard(fn):
    """Wrap an async verb so every exception leaves it as a ToolError."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 -- funnelled into ToolError
            raise translate(e) from None

    return wrapper
