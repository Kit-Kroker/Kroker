"""The pinned Hindsight API surface.

Every path here was read out of the running container's /openapi.json (vendored
to tests/fixtures/hindsight-openapi.json), not out of the published docs, which
contradict each other and the container on retain's path. Task 1 of the plan in
docs/superpowers/plans/2026-08-02-hindsight-real-integration.md records each
resolution; tests/test_hindsight_api_constants.py asserts each constant still
exists in that schema, so a client cannot drift back into calling an endpoint
nobody serves.

Three facts the schema pinned that contradict earlier assumptions:

- The tenant segment is the literal ``default`` in every served path. Constants
  keep ``{tenant}`` so a configured tenant still substitutes through ``_path``
  (and the default ``"default"`` round-trips to the served URL); the contract
  test matches structurally rather than literally so ``{tenant}`` lines up with
  the schema's literal ``default``.
- Retain is ``POST .../memories``, not ``.../memories/retain``. The published
  docs split on this; the container does not serve a retain sub-path.
- Operations are bank-scoped (``.../banks/{bank_id}/operations/{operation_id}``),
  not tenant-scoped, so ``OPERATION_PATH`` carries ``{bank}`` unlike the plan's
  original interface sketch.
"""
from __future__ import annotations

from pathlib import Path

SCHEMA_PATH = (Path(__file__).resolve().parents[3]
               / "tests" / "fixtures" / "hindsight-openapi.json")

BANK_PATH = "/v1/{tenant}/banks/{bank}"
RETAIN_PATH = "/v1/{tenant}/banks/{bank}/memories"
RECALL_PATH = "/v1/{tenant}/banks/{bank}/memories/recall"
CONSOLIDATE_PATH = "/v1/{tenant}/banks/{bank}/consolidate"
OPERATION_PATH = "/v1/{tenant}/banks/{bank}/operations/{operation_id}"

# Task 1 Step 4: the recall request has no `limit`-style count field. Results
# are bounded by a token budget via `max_tokens` (default 4096), or coarsely by
# the `budget` enum. The client sends a token budget; RECALL_KEEP * OVER_FETCH
# in hindsight_client is interpreted accordingly.
RECALL_LIMIT_FIELD = "max_tokens"
