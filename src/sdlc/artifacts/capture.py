"""Session capture pipeline (E-38): normalise -> scrub (fail-closed) ->
digest (pre-truncation) -> store full JSONL + digest JSON.

Fail-closed w.r.t. STORAGE: any failure here stores nothing and returns
(None, None) — the coding task itself must still succeed (an observability
bug must not block delivery; SC-5-style strictness applies to what gets
stored). Ordering is strict: scrub runs before any byte touches disk.

016 (ruling R4, D-9): opt-in raw stream capture. SDLC_RAW_STREAM_DIR
writes the UNMODIFIED raw stdout (before normalising) to
<dir>/<safe run_id>/<safe task_id>-a<attempt>.jsonl, inside its own
try/except — a failure stores nothing extra and changes nothing else.
Default off.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from ..core.models import (
    ArtifactRef,
)
from ..harness.base import CodingHarness
from ..harness.models import SessionDigest
from ..harness.session import digest_of, scrub_session, session_to_jsonl
from .store import LocalFileStore

_log = logging.getLogger(__name__)

RAW_STREAM_ENV = "SDLC_RAW_STREAM_DIR"


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def _capture_raw_stream(raw_stdout: str, run_id: str, name: str) -> None:
    """D-9: the raw stream, unmodified, under its own try/except. A
    failure here is logged and swallowed — the normal capture below is
    unaffected (a raw-stream bug must never cost a session its store)."""
    raw_dir = os.environ.get(RAW_STREAM_ENV, "")
    if not raw_dir:
        return
    try:
        target_dir = Path(raw_dir) / _safe(run_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{name}.jsonl"
        target.write_text(raw_stdout, encoding="utf-8")
        _log.info("raw stream captured: %s", target)
    except Exception:
        _log.warning("raw stream capture failed — nothing extra stored", exc_info=True)


def capture_session(
    harness: CodingHarness,
    raw_stdout: str,
    run_id: str,
    task_id: str,
    attempt: int,
) -> tuple[ArtifactRef | None, SessionDigest | None]:
    name = f"{_safe(task_id)}-a{attempt}"
    _capture_raw_stream(raw_stdout, run_id, name)
    try:
        session = harness.normalise_session(raw_stdout)
        session = scrub_session(session)  # fail-closed: before any put
        digest = digest_of(session)  # pre-truncation (OQ-B7)
        store = LocalFileStore()
        ref = store.put(
            "harness_session", run_id, f"{name}.jsonl", session_to_jsonl(session).encode("utf-8")
        )
        store.put(
            "harness_session_digest",
            run_id,
            f"{name}.digest.json",
            digest.model_dump_json(indent=2).encode("utf-8"),
        )
        return ref, digest
    except Exception:
        _log.warning("session capture failed — nothing stored (fail-closed)", exc_info=True)
        return None, None
