"""ABSOLUTE assertions -- the checks that gate (E-82 design doc 4.5, ADR-11).

An output that no longer parses into the role's declared output_type is
broken whatever a rubric says, so this never degrades to advisory.

The output_type is read off the role's real agent.py rather than a hardcoded
map, so a role that changes its type needs no edit here.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

# Absolute: promptfoo loads this file standalone (see provider.py).
from sdlc.agents.loader import _load_build
from sdlc.agents.settings import MODEL_SETTINGS
from sdlc.benchmarks.vetoes import Veto, VetoConfigError, check, parse_vetoes, validate_fields
from sdlc.eval.promptfoo.assertion import RUBRIC_KEY


@cache
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


def validates_as_output_type(output: str, role: str, agents_dir: Path) -> dict:
    t = output_type_for(role, Path(agents_dir))
    name = getattr(t, "__name__", str(t))
    if not output.strip():
        return {
            "pass": False,
            "score": 0.0,
            "reason": f"empty output — cannot validate as {name} "
            f"(check the provider's `error` field)",
        }
    try:
        data = json.loads(output)
        t.model_validate(data)
    except (json.JSONDecodeError, ValidationError, TypeError) as e:
        return {"pass": False, "score": 0.0, "reason": f"output does not validate as {name}: {e}"}
    blank = _blank_required_strings(t, data)
    if blank:
        return {
            "pass": False,
            "score": 0.0,
            "reason": f"{name} validates but required string field(s) "
            f"are blank: {', '.join(blank)}",
        }
    return {"pass": True, "score": 1.0, "reason": f"validates as {name}"}


def load_vetoes(case: str, role: str, cases_root: Path) -> list[Veto]:
    """Vetoes registered for (case, role), or [] when none are.

    Absence is NOT an error: vetoes are opt-in per case and the absolute tier
    keeps its previous behaviour without them. A veto file that is REGISTERED
    but malformed IS an error -- a veto that does not parse is not a passing
    veto.
    """
    case_yaml = Path(cases_root) / case / "case.yaml"
    if not case_yaml.is_file():
        return []
    data = yaml.safe_load(case_yaml.read_text(encoding="utf-8")) or {}
    rel = (data.get("vetoes") or {}).get(RUBRIC_KEY.get(role, role))
    if not rel:
        return []
    path = Path(cases_root) / case / rel
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise VetoConfigError(f"veto file {path} named in {case_yaml} does not exist") from e
    return parse_vetoes(text)


def get_assert(output: str, context) -> dict:
    """promptfoo's Python assertion entry point -- the name is fixed by
    promptfoo (`getattr(script_module, "get_assert")`). Returns a
    GradingResult dict: {pass, score, reason}."""
    v = (
        context if isinstance(context, dict) else {"vars": getattr(context, "vars", {}) or {}}
    ).get("vars", {})
    role, agents_dir = v["role"], Path(v["agents_dir"])

    # Type validity first: an output that does not parse is broken whatever a
    # veto says, and a veto message about never-populated fields would only
    # obscure that.
    result = validates_as_output_type(output, role, agents_dir)
    if not result["pass"]:
        return result

    try:
        vetoes = load_vetoes(v["case"], role, Path(v["cases_root"]))
        validate_fields(vetoes, output_type_for(role, agents_dir))
    except VetoConfigError as e:
        return {"pass": False, "score": 0.0, "reason": f"veto configuration error: {e}"}

    failures = check(json.loads(output), vetoes)
    if failures:
        return {
            "pass": False,
            "score": 0.0,
            "reason": "; ".join(f"veto {f.veto_id}: {f.reason}" for f in failures),
        }
    return result
