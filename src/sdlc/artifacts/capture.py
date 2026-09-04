"""Session capture pipeline (E-38): normalise -> scrub (fail-closed) ->
digest (pre-truncation) -> store full JSONL + digest JSON.

Fail-closed w.r.t. STORAGE: any failure here stores nothing and returns
(None, None) — the coding task itself must still succeed (an observability
bug must not block delivery; SC-5-style strictness applies to what gets
stored). Ordering is strict: scrub runs before any byte touches disk.
"""

from __future__ import annotations

import logging
import re

from ..core.models import (
    ArtifactRef,
)
from ..harness.adapters import CodingHarness
from ..harness.models import SessionDigest
from ..harness.session import digest_of, scrub_session, session_to_jsonl
from .store import LocalFileStore

_log = logging.getLogger(__name__)


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def capture_session(
    harness: CodingHarness,
    raw_stdout: str,
    run_id: str,
    task_id: str,
    attempt: int,
) -> tuple[ArtifactRef | None, SessionDigest | None]:
    try:
        session = harness.normalise_session(raw_stdout)
        session = scrub_session(session)  # fail-closed: before any put
        digest = digest_of(session)  # pre-truncation (OQ-B7)
        store = LocalFileStore()
        name = f"{_safe(task_id)}-a{attempt}"
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
