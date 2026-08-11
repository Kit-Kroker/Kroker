"""ABSOLUTE assertions -- the checks that gate (E-82 design doc 4.5, ADR-11).

An output that no longer parses into the role's declared output_type is
broken whatever a rubric says, so this never degrades to advisory.

The output_type is read off the role's real agent.py rather than a hardcoded
map, so a role that changes its type needs no edit here.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ValidationError

from ...agents.loader import _load_build
from ...agents.roles import MODEL_SETTINGS


@lru_cache(maxsize=None)
def output_type_for(role: str, agents_dir: Path) -> type[BaseModel]:
    """Build the role's agent with a throwaway model id and read its declared
    output type. No model call happens -- Agent construction is lazy."""
    build = _load_build(role, agents_dir / role)
    agent = build("test", "", MODEL_SETTINGS)
    return agent.output_type


def _blank_required_strings(t: type[BaseModel], data: dict) -> list[str]:
    """Required fields typed `str` that are blank.

    Only strings are checked. A required LIST may legitimately be empty --
    ClarifiedRequirements.open_questions == [] means "nothing to ask" -- and
    failing on that would invent regressions the prompt did not cause.
    """
    schema = t.model_json_schema()
    props = schema.get("properties", {})
    out = []
    for name in schema.get("required", []):
        if props.get(name, {}).get("type") != "string":
            continue
        value = data.get(name)
        if isinstance(value, str) and not value.strip():
            out.append(name)
    return out


def validates_as_output_type(output: str, role: str,
                             agents_dir: Path) -> dict:
    t = output_type_for(role, Path(agents_dir))
    name = getattr(t, "__name__", str(t))
    if not output.strip():
        return {"pass": False, "score": 0.0,
                "reason": f"empty output — cannot validate as {name} "
                          f"(check the provider's `error` field)"}
    try:
        data = json.loads(output)
        t.model_validate(data)
    except (json.JSONDecodeError, ValidationError, TypeError) as e:
        return {"pass": False, "score": 0.0,
                "reason": f"output does not validate as {name}: {e}"}
    blank = _blank_required_strings(t, data)
    if blank:
        return {"pass": False, "score": 0.0,
                "reason": f"{name} validates but required string field(s) "
                          f"are blank: {', '.join(blank)}"}
    return {"pass": True, "score": 1.0, "reason": f"validates as {name}"}


def main() -> None:
    import sys
    ctx = json.loads(sys.argv[2])
    v = ctx.get("vars", {})
    print(json.dumps(validates_as_output_type(
        sys.argv[1], v["role"], Path(v["agents_dir"]))))


if __name__ == "__main__":
    main()
