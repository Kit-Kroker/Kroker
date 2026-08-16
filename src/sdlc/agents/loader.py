"""Agent registry (FR-201) + the ADR-6 anti-collusion validator (FR-204).

The registry is a directory of role folders (agents/<role>/), one per role,
where the directory name IS the role name. Loading it and running
validate_registry() at worker boot is what gives the model-family inequality
invariant teeth — a same-family dev/reviewer config cannot boot a worker.

Resolution deliberately contains no __file__: the registry's location has no
relationship to where this package is installed. Under `pip install .` the
package lands in site-packages, which is why the old
parents[3]/config/agents.yaml walk resolved to a path that never existed in
the image. Order: explicit arg -> $SDLC_AGENTS_DIR -> repo-root discovery.
"""
from __future__ import annotations

import importlib.util
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from ..models import RoleConfig

if TYPE_CHECKING:                       # pydantic_ai import is not free
    from pydantic_ai import Agent

AGENTS_DIR_ENV = "SDLC_AGENTS_DIR"
# Renamed from SDLC_AGENTS_CONFIG: the value's meaning changed from a single
# YAML file to a directory. Accepting the old name silently would let a stale
# value resolve a file where a directory is expected and fail somewhere less
# obvious than boot.
LEGACY_AGENTS_ENV = "SDLC_AGENTS_CONFIG"

# Marker files that identify a repo checkout. Two, not one: `pyproject.toml`
# alone matches any Python project we happen to be cwd'd into.
_ROOT_MARKERS = ("pyproject.toml", "agents/registry.yaml")

# Harness-execution roles. Keys fixed by DevTask.role
# (Literal["dev","test","devops"], models.py:144). PipelineConfig.roles
# mirrors exactly this set — see _validate_pipeline_mirror.
HARNESS_ROLES = frozenset({"dev", "test", "devops"})

# Proposer roles, one per agent in agents/roles.py. 'devops_planner' PLANS
# devops tasks; the 'devops' harness role above RUNS them.
PROPOSER_ROLES = frozenset({
    "clarify", "architect", "planner", "qa", "reviewer", "analyst",
    "merge_verdict", "devops_planner",
})

REQUIRED_ROLES = HARNESS_ROLES | PROPOSER_ROLES

# Roles the pipeline can run WITHOUT, but which are still known directories.
# 'research' is the first entry: research_enabled defaults False so the
# pipeline boots without running the stage, but agents/research/ is still a
# KNOWN directory so the unknown-directory check keeps biting. This EXTENDS
# the fail-closed check; it does not weaken it. 'discover' joins for the same
# reason at a different tier (E-48 DD7): it is an ASSESSMENT-only role, and
# making it required would fail boot on a feature-only deployment. 'risk'
# joins it for the identical reason at the next phase (E-49 RD7).
OPTIONAL_ROLES: frozenset[str] = frozenset(
    {"research", "deep_review", "handoff", "adversary", "discover", "risk"})

# REQUIRED_ROLES gates PRESENCE (a missing one fails boot).
# KNOWN_ROLES gates RECOGNITION (an unknown directory fails boot).
KNOWN_ROLES = REQUIRED_ROLES | OPTIONAL_ROLES


class RegistryError(ValueError):
    """A registry that violates a structural invariant (missing role, or an
    ADR-6 same-family developer/reviewer pairing)."""


def model_family(model: str) -> str:
    """Provider/family prefix of a Pydantic AI model id. Splits on the first
    ':' or '/': 'anthropic:glm-5.2' -> 'anthropic';
    'zai-coding-plan/glm-5.2' -> 'zai-coding-plan'. Case-insensitive."""
    return re.split(r"[:/]", model, maxsplit=1)[0].strip().lower()


def model_id(model: str) -> str:
    """The model itself, with any provider prefix stripped:
    'anthropic:glm-5.2' -> 'glm-5.2'; 'zai-coding-plan/glm-5.2' -> 'glm-5.2'.
    A string with no separator IS the id. Case-insensitive.

    model_family() answers "who serves it"; this answers "what is it". The
    adversary's constraint needs the second: two prefixes over the same
    weights decorrelate nothing.
    """
    parts = re.split(r"[:/]", model, maxsplit=1)
    return parts[-1].strip().lower()


def _discover_agents_dir() -> Path | None:
    """Walk up from cwd for a checkout containing BOTH marker files. Dev and
    tests only — production sets $SDLC_AGENTS_DIR explicitly."""
    for d in (Path.cwd(), *Path.cwd().parents):
        if all((d / m).is_file() for m in _ROOT_MARKERS):
            return d / "agents"
    return None


def _resolve_agents_dir(path: str | os.PathLike | None = None) -> Path:
    if os.environ.get(LEGACY_AGENTS_ENV):
        raise RegistryError(
            f"{LEGACY_AGENTS_ENV} was renamed to {AGENTS_DIR_ENV} and now names "
            f"a DIRECTORY (the registry is agents/<role>/, not one YAML file). "
            f"Unset {LEGACY_AGENTS_ENV} and set {AGENTS_DIR_ENV}.")
    if path is not None:
        return Path(path)
    env = os.environ.get(AGENTS_DIR_ENV)
    if env:
        return Path(env)
    found = _discover_agents_dir()
    if found is not None:
        return found
    raise RegistryError(
        f"cannot locate the agents registry. Tried: an explicit path argument; "
        f"${AGENTS_DIR_ENV}; and walking up from {Path.cwd()} for a directory "
        f"containing both pyproject.toml and agents/registry.yaml.")


def _parse(path: str | os.PathLike | None = None) -> dict[str, RoleConfig]:
    """Walk the registry directory into {role_name: RoleConfig}, UNVALIDATED.
    Private: callers go through load_registry, which validates."""
    root = _resolve_agents_dir(path)
    if not root.is_dir():
        raise RegistryError(f"agents registry is not a directory: {root}")

    reg = root / "registry.yaml"
    if not reg.is_file():
        raise RegistryError(
            f"missing {reg}: every registry declares its version")
    version = (yaml.safe_load(reg.read_text(encoding="utf-8")) or {}).get("version")
    if version != 1:
        raise RegistryError(
            f"unsupported registry version {version!r} in {reg}; expected 1")

    roles: dict[str, RoleConfig] = {}
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        roles[d.name] = _parse_role(d.name, d)
    return roles


def _parse_role(name: str, d: Path) -> RoleConfig:
    if name not in KNOWN_ROLES:
        raise RegistryError(
            f"unknown role directory '{name}' in {d.parent}: the directory name "
            f"is the role name, so this is a typo, not an extension point. "
            f"Known roles: {', '.join(sorted(KNOWN_ROLES))}")
    f = d / "agent.yaml"
    if not f.is_file():
        raise RegistryError(f"role '{name}': missing {f}")
    data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    declared = data.pop("role", None)
    if declared is not None and declared != name:
        raise RegistryError(
            f"role directory '{name}' contains an agent.yaml declaring role "
            f"'{declared}': the filename is the API and must agree with its "
            f"contents")
    cfg = RoleConfig(**data)
    instructions_file = d / "instructions.md"
    needs_prompt = cfg.kind != "harness"
    if needs_prompt:
        if not instructions_file.is_file():
            raise RegistryError(f"role '{name}': missing {instructions_file}")
        # read_text applies universal newlines, so a CRLF checkout still
        # hashes as LF (tests/test_prompt_migration.py pins this).
        text = instructions_file.read_text(encoding="utf-8")
        if not text.strip():
            raise RegistryError(
                f"role '{name}': {instructions_file} is empty — an empty system "
                f"prompt is a boot-time bug, not a runtime surprise")
        cfg = cfg.model_copy(update={"instructions": text})
        if not (d / "agent.py").is_file():
            raise RegistryError(f"role '{name}': missing {d / 'agent.py'}")
        if cfg.kind == "research":
            tools_dir = d / "tools"
            if not tools_dir.is_dir():
                raise RegistryError(
                    f"role '{name}' is kind=research and must carry a tools/ "
                    f"directory (it is the only role that may): {tools_dir}")
            tool_files = _validate_tool_files(name, tools_dir)
            cfg = cfg.model_copy(update={"tool_files": tool_files})
    elif instructions_file.exists() or (d / "agent.py").exists():
        raise RegistryError(
            f"role '{name}' is kind=harness and carries instructions.md or "
            f"agent.py, which would never be read: silent dead config")
    return cfg


def load_registry(path: str | os.PathLike | None = None) -> dict[str, RoleConfig]:
    """Parse AND validate. No unvalidated registry escapes this module, so
    roles.py's import-time call fails with a RegistryError explaining the
    problem rather than a KeyError from whichever role it indexed first."""
    roles = _parse(path)
    validate_registry(roles)
    return roles


def check_adr6_families(role_models: dict[str, str]) -> None:
    """The ADR-6 model-family inequality invariant, over a resolved
    role->model map. `dev` and `reviewer` must differ in family; if
    `deep_review` is present it must differ from `dev`. This is the single
    implementation reused at boot (validate_registry) and per run
    (validate_run_roles)."""
    dev = role_models.get("dev")
    rev = role_models.get("reviewer")
    if dev is None or rev is None:
        raise RegistryError(
            "ADR-6 check requires both 'dev' and 'reviewer' models")
    if model_family(dev) == model_family(rev):
        raise RegistryError(
            f"ADR-6 violation: reviewer family '{model_family(rev)}' "
            f"equals the family of 'dev' — anti-collusion review requires a "
            f"different model family than the developer's authoring model")
    dr = role_models.get("deep_review")
    if dr is not None and model_family(dr) == model_family(dev):
        raise RegistryError(
            f"ADR-6 violation: deep_review family '{model_family(dr)}' "
            f"equals the family of 'dev' — the transcript lens must not "
            f"correlate with the authoring model")


def check_adversary_model(role_models: dict[str, str]) -> None:
    """The adversary must not BE either model it is decorrelating from.

    Deliberately by model id, not family: the shipped registry runs `dev`
    and `reviewer` on the same glm-5.2 behind different providers, so a
    family check here would wave through a second copy of the reviewer.
    (That dev/reviewer pairing is spec OQ-A4 and is NOT changed here --
    check_adr6_families keeps its existing semantics so no benchmark
    baseline shifts.) No-op when the optional role is absent.
    """
    adv = role_models.get("adversary")
    if adv is None:
        return
    for other in ("dev", "reviewer"):
        peer = role_models.get(other)
        if peer is not None and model_id(adv) == model_id(peer):
            raise RegistryError(
                f"ADR-6 violation: adversary model '{adv}' is the same model "
                f"as '{other}' ('{peer}') -- a second opinion from the same "
                f"weights is not a second opinion")


def validate_run_roles(role_models: dict[str, str]) -> None:
    """Per-run ADR-6 enforcement at a boundary that constructs a non-default
    role→model map (benchmark arm, CLI --role-model). Registry-structural
    checks (harness inequality, research provider) stay at boot; this guards
    only what a per-run override can break: model-family inequality."""
    check_adr6_families(role_models)
    check_adversary_model(role_models)


def validate_registry(roles: dict[str, RoleConfig]) -> None:
    """Fail closed on any structural violation.

    Checks run in this order deliberately: a missing role is reported as
    itself, before any downstream check trips over its absence.

    The ADR-6 invariant is model-family inequality between the reviewer and
    'dev' — the role feature.py:434 resolves to actually write code. (It is
    NOT harness inequality; that clause applies only to the optional
    deep-review harness reviewer tier.)
    """
    missing = sorted(REQUIRED_ROLES - set(roles))
    if missing:
        raise RegistryError(
            f"registry is missing required role(s): {', '.join(missing)}")
    for name in ("dev", "reviewer"):
        if roles[name].model is None:
            raise RegistryError(f"role '{name}' must declare a model")
    dev, rev = roles["dev"], roles["reviewer"]
    role_models = {"dev": dev.model, "reviewer": rev.model}
    if "deep_review" in roles:
        if roles["deep_review"].model is None:
            raise RegistryError("role 'deep_review' must declare a model")
        role_models["deep_review"] = roles["deep_review"].model
    check_adr6_families(role_models)
    check_adversary_model({n: c.model for n, c in roles.items()
                           if c.model is not None})
    if rev.kind == "harness" and rev.harness is not None \
            and rev.harness == dev.harness:
        raise RegistryError(
            "deep-review harness reviewer must use a different harness than "
            "the developer")
    for name, cfg in roles.items():
        if cfg.kind != "research":
            continue
        if cfg.provider is None:
            raise RegistryError(
                f"role '{name}' is kind=research and must name a provider "
                f"(tavily, exa, or fake); ADR-6 does not apply — it reviews "
                f"nothing")
        if cfg.provider == "tavily" and not os.environ.get("TAVILY_API_KEY"):
            raise RegistryError(
                f"role '{name}' declares provider: tavily but TAVILY_API_KEY is "
                f"not set — fail closed. Use provider: fake for CI/offline.")
        if cfg.provider == "exa" and not os.environ.get("EXA_API_KEY"):
            raise RegistryError(
                f"role '{name}' declares provider: exa but EXA_API_KEY is "
                f"not set — fail closed. Use provider: fake for CI/offline.")
    _validate_pipeline_mirror(roles)


def _validate_pipeline_mirror(roles: dict[str, RoleConfig]) -> None:
    """the agents/ registry is authoritative; PipelineConfig.roles is a
    purity-mandated mirror of its harness roles (see the note on
    PipelineConfig.roles). Drift between them is what let ADR-6 validate a role
    that never ran, so it fails the worker at boot."""
    from ..models import PipelineConfig      # local: avoid an import cycle at
                                             # module scope via models -> ...
    default_roles = PipelineConfig().roles
    if set(default_roles) != HARNESS_ROLES:
        raise RegistryError(
            f"PipelineConfig.roles must mirror exactly the harness roles "
            f"{sorted(HARNESS_ROLES)}; it has {sorted(default_roles)}")
    for name in sorted(HARNESS_ROLES):
        reg, dflt = roles[name], default_roles[name]
        if (reg.kind, reg.harness, reg.model) != \
                (dflt.kind, dflt.harness, dflt.model):
            raise RegistryError(
                f"PipelineConfig.roles['{name}'] does not mirror the agents/ "
                f"registry: "
                f"registry has (kind={reg.kind}, harness={reg.harness}, "
                f"model={reg.model}); PipelineConfig default has "
                f"(kind={dflt.kind}, harness={dflt.harness}, "
                f"model={dflt.model})")


def _load_build(name: str, d: Path):
    """Import agents/<role>/agent.py by PATH under a private module name, so
    no `agents` package is created and nothing resolves against the code
    package src/sdlc/agents/."""
    f = d / "agent.py"
    spec = importlib.util.spec_from_file_location(f"_sdlc_agent_{name}", f)
    if spec is None or spec.loader is None:
        raise RegistryError(f"role '{name}': cannot load {f}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise RegistryError(f"role '{name}': {f} failed to import: {exc}") from exc
    build = getattr(module, "build", None)
    if not callable(build):
        raise RegistryError(
            f"role '{name}': {f} defines no callable build(model, "
            f"instructions, model_settings)")
    return build


def _validate_tool_files(role: str, tools_dir: Path) -> list[str]:
    """Structurally validate each tools/*.py WITHOUT importing it: exactly one
    top-level function whose name == the filename stem, with every parameter and
    the return fully annotated. Returns absolute paths. Import happens later, in
    build_agents, only after the whole registry has validated."""
    import ast

    paths: list[str] = []
    for f in sorted(tools_dir.glob("*.py")):
        if f.name == "__init__.py":
            continue
        stem = f.stem
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        funcs = [n for n in tree.body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if not any(fn.name == stem for fn in funcs):
            raise RegistryError(
                f"role '{role}': tool file {f.name} defines no function named "
                f"'{stem}' — the filename is the API (mismatch)")
        fn = next(fn for fn in funcs if fn.name == stem)
        args = fn.args
        params = [*args.posonlyargs, *args.args, *args.kwonlyargs]
        unannotated = [a.arg for a in params if a.annotation is None]
        if unannotated or fn.returns is None:
            raise RegistryError(
                f"role '{role}': tool '{stem}' has an unannotated signature "
                f"(params={unannotated}, return_annotated={fn.returns is not None})"
                f" — tool signatures must be fully typed")
        paths.append(str(f.resolve()))
    if not paths:
        raise RegistryError(
            f"role '{role}': tools/ is empty — a research role with no tools "
            f"cannot fetch anything")
    return paths


def build_agents(roles: dict[str, RoleConfig], model_settings,
                 agents_dir: str | os.PathLike | None = None
                 ) -> dict[str, "Agent"]:
    """Construct every proposer role's Agent from its own agent.py.

    MUST be called only AFTER load_registry() has returned: validation precedes
    import (see the module docstring). Keyed by ROLE name — an agent's own
    .name is its Temporal activity name and is NOT derived from the role
    ('qa' -> qa_analyst_agent, 'devops_planner' -> devops_agent).

    model_settings is a parameter rather than an import from roles.py: roles.py
    imports this function, so importing back would be a cycle that only works
    by definition order.

    agents_dir is a parameter rather than a re-resolution: the caller knows
    which tree it loaded, and re-resolving would import agent.py from the
    shipped registry while validating a different one.
    """
    root = Path(agents_dir) if agents_dir is not None \
        else _resolve_agents_dir(None)
    agents: dict[str, "Agent"] = {}
    seen: dict[str, str] = {}
    for name, cfg in roles.items():
        if cfg.kind == "harness":
            continue
        build = _load_build(name, root / name)
        if cfg.kind == "research":
            # Research build takes its tool paths and provider name too. Tool
            # modules are imported HERE — after the whole registry validated
            # (validation precedes import; registry spec finding 3).
            agent = build(cfg.model, cfg.instructions, model_settings,
                          cfg.tool_files, cfg.provider)
        else:
            agent = build(cfg.model, cfg.instructions, model_settings)
        if agent.name in seen:
            raise RegistryError(
                f"roles '{seen[agent.name]}' and '{name}' both build an agent "
                f"named '{agent.name}': colliding Temporal activity names")
        seen[agent.name] = name
        agents[name] = agent
    return agents
