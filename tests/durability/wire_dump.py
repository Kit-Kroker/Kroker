"""Wire dump for one no-override FeatureWorkflow run (004 T003, FR-010).

Records, from a single greenfield_happy capture on the fakes (the replay
suite's own scenario and starter), exactly what the wire-neutrality contract
cares about:

- the ordered list of scheduled activity names (every
  ActivityTaskScheduled event, in order), and
- the ``model_id`` carried by each ``agent__<name>__model_request`` input.

Decoding note: the model_request input's params payload is serialized by the
installed pydantic-ai transport as ``json/plain`` (it is the frozen dataclass
``ModelRequestParams`` — messages / model_id / model_settings /
model_request_parameters / serialized_run_context — carried as plain JSON
with no pydantic-class metadata), so the decode is a JSON parse of the
payload, not the typed ``payload_converter.from_payloads`` the priced-usage
parity test uses for its pydantic inputs. The payload is reached through the
same history-event walk as this suite's other parity tests.

The dump is deliberately free of run ids, timestamps and message payloads:
names and model ids only, so the frozen fixture is byte-stable across runs.
Regeneration is guarded behind $SDLSC_WIRE_REGEN=1 — the neutrality test
loads the fixture and never rewrites it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from temporalio.client import WorkflowHistory

from tests.replay.harness import FEATURE_STARTER, capture
from tests.replay.scenarios import SCENARIOS

FIXTURE = Path(__file__).parent / "fixtures" / "wire_no_override.json"
REGEN_ENV = "SDLSC_WIRE_REGEN"

_MODEL_REQUEST_SUFFIX = "__model_request"


def _model_request_model_id(payload) -> str:
    """The ``model_id`` of one model_request params payload, as written by
    the caller (registry string, or an override string once 004 forwards
    one). Raises — never returns ``None`` — if the payload shape drifts: a
    missing, empty or non-string ``model_id`` is an encoding change, and a
    silent null here would let the fixture freeze a vacuous baseline."""
    encoding = payload.metadata.get("encoding", b"").decode()
    if encoding not in ("json/plain", "json"):
        raise AssertionError(f"model_request params payload is {encoding!r}, not JSON")
    params = json.loads(payload.data)
    model_id = params.get("model_id")
    if not isinstance(model_id, str) or not model_id:
        raise AssertionError(
            f"model_request params payload carries no usable model_id (got "
            f"{model_id!r}) — the payload encoding changed; the dump must "
            "fail loudly, not record null"
        )
    return model_id


def dump_wire(history: WorkflowHistory) -> dict[str, Any]:
    """Project one captured history onto the wire-neutrality fixture shape."""
    activities: list[str] = []
    model_requests: list[dict[str, str]] = []
    for ev in history.events:
        if not ev.HasField("activity_task_scheduled_event_attributes"):
            continue
        attrs = ev.activity_task_scheduled_event_attributes
        name = attrs.activity_type.name
        activities.append(name)
        if name.endswith(_MODEL_REQUEST_SUFFIX):
            payloads = list(attrs.input.payloads)
            model_requests.append(
                {"activity": name, "model_id": _model_request_model_id(payloads[0])}
            )
    return {"activities": activities, "model_requests": model_requests}


async def capture_no_override_wire(monkeypatch: Any, tmp_path: Path) -> dict[str, Any]:
    """Run ONE no-override greenfield_happy FeatureWorkflow capture on the
    fakes and return its wire dump."""
    scenario = next(s for s in SCENARIOS if s.name == "greenfield_happy")
    captured = await capture(scenario, FEATURE_STARTER, monkeypatch, tmp_path)
    return dump_wire(captured.history)


def write_fixture(dump: dict[str, Any]) -> None:
    FIXTURE.parent.mkdir(exist_ok=True)
    FIXTURE.write_text(json.dumps(dump, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))
