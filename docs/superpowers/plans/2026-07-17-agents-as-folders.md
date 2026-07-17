# Agents as Folders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `config/agents.yaml` with an `agents/<role>/` directory registry where each proposer role owns its `agent.yaml`, `instructions.md` and `agent.py` — and make the registry actually reach a pip-installed worker.

**Architecture:** Three tasks, each landing green and independently reviewable. Task 1 moves the storage medium and fixes registry resolution (which is broken in the image today). Task 2 moves prompts into `instructions.md`. Task 3 distributes `Agent(...)` construction into per-role `agent.py`. `validate_registry()` is never re-implemented — it is re-fed the same `dict[str, RoleConfig]` it receives today.

**Tech Stack:** Python 3.11+, Pydantic v2, pydantic-ai 2.5, PyYAML, Temporal, pytest.

**Spec:** `docs/superpowers/specs/2026-07-17-agents-as-folders-design.md`

## Global Constraints

- **This is a strict refactor.** Same eleven roles, same `RoleConfig`, same boot failure on a same-family pairing. Only the storage medium and the construction site change.
- **`PROMPT_SHAS` values MUST NOT move.** Every hash is over the same bytes before and after. Pinned in Task 2. A changed value is a bug, never an improvement.
- **Agent `name` values MUST NOT move.** They are Temporal activity names. `roles.py`: *"never rename after deploying to production."* Pinned in Task 3.
- **Role name ≠ agent name.** Role `qa` builds `qa_analyst_agent`; role `devops_planner` builds `devops_agent`. Verified at HEAD.
- **Validate everything, then import anything.** No `agent.py` may be imported before `validate_registry()` has returned.
- **Do not touch:** ADR-6's check, `_validate_pipeline_mirror`, `STAGE_MODELS`, `STAGE_ROLES`, `PROMPT_SHAS`' keyspace, `content_key`, `worker.py`, `feature.py`, or the module-level names they import (`clarify_agent`, `t_clarify`, `ALL_TEMPORAL_AGENTS`, …).
- **`agents/` is repo-root**, one word from the code package `src/sdlc/agents/`. Modules load by file path under a private module name, never by package name.
- **Importing `roles.py` requires `ANTHROPIC_API_KEY`** — `Agent(...)` infers its provider eagerly. Use `ANTHROPIC_API_KEY=dummy` for any one-off script that imports it.
- **Write asset files as bytes**, never `write_text`, to defeat Windows newline translation. The repo has `autocrlf` behaviour (git warns "LF will be replaced by CRLF"), so the loader normalises newlines on read and a test proves CRLF and LF hash identically.
- Run the full suite with `python -m pytest` from the repo root. Baseline at plan time: **353 passed**.

---

### Task 1: `agents/` directory registry + resolution that survives a real install

Moves the registry from one YAML file to eleven directories, and deletes the `parents[3]` path walk that makes the containerised worker unbootable (spec finding 9). Prompts stay Python constants in this task; `agent.yaml` is the only file per role.

**Files:**
- Create: `agents/registry.yaml`
- Create: `agents/{dev,test,devops,clarify,architect,planner,qa,reviewer,analyst,merge_verdict,devops_planner}/agent.yaml` (11 files)
- Modify: `src/sdlc/agents/loader.py` (lines 1–21 header/constants, `_parse`)
- Modify: `Dockerfile:11-13`
- Modify: `.env.example`
- Delete: `config/agents.yaml`
- Test: `tests/test_agents_registry.py`, `tests/test_registry_resolution.py` (new)

**Interfaces:**
- Consumes: `RoleConfig` (`src/sdlc/models.py:301`), `REQUIRED_ROLES`/`HARNESS_ROLES`/`PROPOSER_ROLES` (`loader.py`), `RegistryError`.
- Produces:
  - `OPTIONAL_ROLES: frozenset[str]` — empty here; the research spec's only entry point.
  - `KNOWN_ROLES: frozenset[str]` = `REQUIRED_ROLES | OPTIONAL_ROLES`.
  - `AGENTS_DIR_ENV = "SDLC_AGENTS_DIR"`, `LEGACY_AGENTS_ENV = "SDLC_AGENTS_CONFIG"`.
  - `_resolve_agents_dir(path: str | os.PathLike | None) -> Path`
  - `_parse(path) -> dict[str, RoleConfig]` — signature unchanged; reads directories.
  - `load_registry(path) -> dict[str, RoleConfig]` — signature and validate-then-return behaviour unchanged.

- [ ] **Step 1: Write the failing resolution tests**

Create `tests/test_registry_resolution.py`:

```python
"""Registry resolution must not depend on where the CODE is installed.

`DEFAULT_AGENTS_CONFIG = Path(__file__).resolve().parents[3] / "config" /
"agents.yaml"` worked only because the local install is editable. Under
`pip install .` the package lands in site-packages and parents[3] is
/usr/local/lib/python3.13 — so the image could never boot. These tests pin the
replacement: explicit arg -> $SDLC_AGENTS_DIR -> repo-root discovery -> a
RegistryError that names all three.
"""
import pytest

from sdlc.agents.loader import (
    AGENTS_DIR_ENV, LEGACY_AGENTS_ENV, RegistryError, _resolve_agents_dir,
)


def test_explicit_path_wins_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv(AGENTS_DIR_ENV, str(tmp_path / "from_env"))
    assert _resolve_agents_dir(tmp_path / "explicit") == tmp_path / "explicit"


def test_env_var_used_when_no_explicit_path(tmp_path, monkeypatch):
    monkeypatch.setenv(AGENTS_DIR_ENV, str(tmp_path / "from_env"))
    assert _resolve_agents_dir(None) == tmp_path / "from_env"


def test_repo_root_discovered_by_marker_files(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "agents").mkdir(parents=True)
    (root / "pyproject.toml").write_bytes(b"[project]\n")
    (root / "agents" / "registry.yaml").write_bytes(b"version: 1\n")
    nested = root / "src" / "deep"
    nested.mkdir(parents=True)
    monkeypatch.delenv(AGENTS_DIR_ENV, raising=False)
    monkeypatch.chdir(nested)                      # discovery walks UP from cwd
    assert _resolve_agents_dir(None) == root / "agents"


def test_unresolvable_raises_registry_error_naming_all_mechanisms(
        tmp_path, monkeypatch):
    monkeypatch.delenv(AGENTS_DIR_ENV, raising=False)
    monkeypatch.chdir(tmp_path)                    # no markers anywhere above
    with pytest.raises(RegistryError) as exc:
        _resolve_agents_dir(None)
    msg = str(exc.value)
    assert AGENTS_DIR_ENV in msg
    assert "pyproject.toml" in msg
    assert "registry.yaml" in msg


def test_legacy_env_var_raises_rather_than_being_ignored(tmp_path, monkeypatch):
    """SDLC_AGENTS_CONFIG named a FILE; SDLC_AGENTS_DIR names a DIRECTORY.
    Silently ignoring the old name would let a stale value fail later and
    less clearly."""
    monkeypatch.setenv(LEGACY_AGENTS_ENV, str(tmp_path / "agents.yaml"))
    with pytest.raises(RegistryError, match=AGENTS_DIR_ENV):
        _resolve_agents_dir(None)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/test_registry_resolution.py -v`
Expected: FAIL — `ImportError: cannot import name 'AGENTS_DIR_ENV' from 'sdlc.agents.loader'`

- [ ] **Step 3: Replace the loader's header and resolution**

In `src/sdlc/agents/loader.py`, replace the module docstring and lines 18–21 (`AGENTS_CONFIG_ENV`, the `DEFAULT_AGENTS_CONFIG` comment, `DEFAULT_AGENTS_CONFIG`) with:

```python
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

import os
import re
from pathlib import Path

import yaml

from ..models import RoleConfig

AGENTS_DIR_ENV = "SDLC_AGENTS_DIR"
# Renamed from SDLC_AGENTS_CONFIG: the value's meaning changed from a single
# YAML file to a directory. Accepting the old name silently would let a stale
# value resolve a file where a directory is expected and fail somewhere less
# obvious than boot.
LEGACY_AGENTS_ENV = "SDLC_AGENTS_CONFIG"

# Marker files that identify a repo checkout. Two, not one: `pyproject.toml`
# alone matches any Python project we happen to be cwd'd into.
_ROOT_MARKERS = ("pyproject.toml", "agents/registry.yaml")
```

Then add, immediately after `model_family()`:

```python
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
```

- [ ] **Step 4: Run the resolution tests to verify they pass**

Run: `python -m pytest tests/test_registry_resolution.py -v`
Expected: 5 passed

- [ ] **Step 5: Add the shared registry-tree helper to `tests/conftest.py`**

It lives in `conftest.py`, not in a test module, because **Tasks 2 and 3 each make a new file
mandatory** (`instructions.md`, then `agent.py`). Every task's trees must grow together or the
previous task's tests start failing for a reason that has nothing to do with them. One helper, one
place to extend. `from tests.conftest import run_git` at `tests/test_integration_activities.py:11`
is the established precedent.

Append to `tests/conftest.py`:

```python
_HARNESS_AGENT_YAML = (
    b"kind: harness\nharness: opencode\nmodel: zai-coding-plan/glm-5.2\n")
_PROPOSER_AGENT_YAML = b"kind: proposer\nmodel: anthropic:glm-5.2\n"

HARNESS_ROLE_NAMES = ("dev", "test", "devops")
PROPOSER_ROLE_NAMES = ("clarify", "architect", "planner", "qa", "reviewer",
                       "analyst", "merge_verdict", "devops_planner")


def write_registry_dir(root, version=1):
    """Materialise a VALID agents/ tree. Tests perturb exactly one thing after
    calling this, so each assertion fails for the reason under test.

    Grows with the increment: Task 2 adds instructions.md, Task 3 adds
    agent.py. Keep it valid or every caller breaks at once.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "registry.yaml").write_bytes(f"version: {version}\n".encode())
    for name in HARNESS_ROLE_NAMES:
        d = root / name
        d.mkdir(exist_ok=True)
        (d / "agent.yaml").write_bytes(_HARNESS_AGENT_YAML)
    for name in PROPOSER_ROLE_NAMES:
        d = root / name
        d.mkdir(exist_ok=True)
        (d / "agent.yaml").write_bytes(_PROPOSER_AGENT_YAML)
    return root
```

Then append the directory-walk tests to `tests/test_agents_registry.py`:

```python
from sdlc.agents.loader import KNOWN_ROLES, OPTIONAL_ROLES
from tests.conftest import write_registry_dir as _write_registry_dir


def test_optional_roles_is_empty_and_known_is_their_union():
    """The seam the research spec extends. Empty here on purpose."""
    assert OPTIONAL_ROLES == frozenset()
    assert KNOWN_ROLES == REQUIRED_ROLES | OPTIONAL_ROLES


def test_directory_registry_loads_and_validates(tmp_path):
    root = _write_registry_dir(tmp_path / "agents")
    roles = load_registry(root)
    assert set(roles) == REQUIRED_ROLES
    assert roles["dev"].harness == HarnessKind.OPENCODE
    assert roles["reviewer"].model == "anthropic:glm-5.2"


def test_unknown_role_directory_rejected(tmp_path):
    root = _write_registry_dir(tmp_path / "agents")
    (root / "not_a_role").mkdir()
    (root / "not_a_role" / "agent.yaml").write_bytes(b"kind: proposer\n")
    with pytest.raises(RegistryError, match="not_a_role"):
        load_registry(root)


def test_role_directory_missing_agent_yaml_rejected(tmp_path):
    root = _write_registry_dir(tmp_path / "agents")
    (root / "reviewer" / "agent.yaml").unlink()
    with pytest.raises(RegistryError, match="reviewer"):
        load_registry(root)


def test_agent_yaml_declaring_a_different_role_rejected(tmp_path):
    """The filename is the API; contents disagreeing with it is an error."""
    root = _write_registry_dir(tmp_path / "agents")
    (root / "reviewer" / "agent.yaml").write_bytes(
        b"role: analyst\nkind: proposer\nmodel: anthropic:glm-5.2\n")
    with pytest.raises(RegistryError, match="reviewer"):
        load_registry(root)


def test_missing_registry_yaml_rejected(tmp_path):
    root = _write_registry_dir(tmp_path / "agents")
    (root / "registry.yaml").unlink()
    with pytest.raises(RegistryError, match="registry.yaml"):
        load_registry(root)


def test_unsupported_registry_version_rejected(tmp_path):
    root = _write_registry_dir(tmp_path / "agents", version=99)
    with pytest.raises(RegistryError, match="99"):
        load_registry(root)


def test_adr6_still_bites_through_the_directory_loader(tmp_path):
    """The registry spec's regression test, re-run against directories. This
    is what proves 'strict refactor' rather than aspiration."""
    root = _write_registry_dir(tmp_path / "agents")
    (root / "reviewer" / "agent.yaml").write_bytes(
        b"kind: proposer\nmodel: zai-coding-plan/other\n")   # dev's family
    with pytest.raises(RegistryError, match="family"):
        load_registry(root)
```

- [ ] **Step 6: Run them to verify they fail**

Run: `python -m pytest tests/test_agents_registry.py -v`
Expected: FAIL — `ImportError: cannot import name 'KNOWN_ROLES'`

- [ ] **Step 7: Add the role sets and the directory walk**

In `src/sdlc/agents/loader.py`, after `REQUIRED_ROLES = HARNESS_ROLES | PROPOSER_ROLES`:

```python
# Roles the pipeline can run WITHOUT, but which are still known directories.
# Empty today, named deliberately: a fail-closed unknown-directory check would
# otherwise reject an optional role's folder outright, forcing the next spec to
# weaken this check instead of extending it. The research role is its first
# entry (2026-07-17-research-agent-grounded-briefs-design.md).
OPTIONAL_ROLES: frozenset[str] = frozenset()

# REQUIRED_ROLES gates PRESENCE (a missing one fails boot).
# KNOWN_ROLES gates RECOGNITION (an unknown directory fails boot).
KNOWN_ROLES = REQUIRED_ROLES | OPTIONAL_ROLES
```

Replace `_parse` entirely:

```python
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
    return RoleConfig(**data)
```

- [ ] **Step 8: Run them to verify they pass**

Run: `python -m pytest tests/test_agents_registry.py tests/test_registry_resolution.py -v`
Expected: all passed

- [ ] **Step 9: Materialise the shipped registry**

```bash
mkdir -p agents/{dev,test,devops,clarify,architect,planner,qa,reviewer,analyst,merge_verdict,devops_planner}
printf 'version: 1\n' > agents/registry.yaml
for r in dev test devops; do
  printf 'kind: harness\nharness: opencode\nmodel: zai-coding-plan/glm-5.2\n' > "agents/$r/agent.yaml"
done
for r in clarify architect planner qa reviewer analyst merge_verdict devops_planner; do
  printf 'kind: proposer\nmodel: anthropic:glm-5.2\n' > "agents/$r/agent.yaml"
done
```

Then add the ADR-6 comment that `config/agents.yaml` carried, to `agents/reviewer/agent.yaml`:

```yaml
# ADR-6: model_family(reviewer) != model_family(dev). 'dev' is the role that
# actually writes code (feature.py:434), so it is the one the check constrains.
# Editing a model here is configuration, not a code change (US-4/US-5).
kind: proposer
model: anthropic:glm-5.2
```

And to `agents/devops_planner/agent.yaml`:

```yaml
# PLANS devops tasks (builds devops_agent). The 'devops' harness role RUNS them.
kind: proposer
model: anthropic:glm-5.2
```

- [ ] **Step 10: Delete the old registry and update its consumers**

```bash
git rm config/agents.yaml
rmdir config 2>/dev/null || true
```

In `tests/test_agents_registry.py:41`, update the comment on `test_shipped_registry_loads_and_validates`:

```python
def test_shipped_registry_loads_and_validates():
    roles = load_registry()                      # default: discovered agents/
    assert REQUIRED_ROLES <= set(roles)
    validate_registry(roles)                     # must not raise
```

Delete the two old file-based override tests at `tests/test_agents_registry.py:87` and `:105`/`:117` (they write a tmp `agents.yaml` and set `SDLC_AGENTS_CONFIG`); `tests/test_registry_resolution.py` and the directory tests replace them.

In `src/sdlc/agents/loader.py:103,119` and `src/sdlc/models.py:449`, change the phrase `agents.yaml` to `the agents/ registry` in the docstrings/comments. Behaviour unchanged.

- [ ] **Step 11: Ship the registry in the image**

Replace `Dockerfile` lines 11–13:

```dockerfile
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
# The registry is an asset, not code: pip install only takes src/, so without
# this COPY the worker cannot boot (it loads the registry at import).
COPY agents ./agents
RUN pip install --no-cache-dir .

ENV TEMPORAL_HOST=temporal:7233
ENV SDLC_WORKTREES_ROOT=/tmp/sdlc/worktrees
# Explicit, not left to cwd-discovery: WORKDIR /app would make discovery
# appear to work, so the two mechanisms would mask each other and the first
# `docker run -w /somewhere-else` would fail in production, not in CI.
ENV SDLC_AGENTS_DIR=/app/agents
```

Add to `.env.example` under `# --- Tunables (optional) ---`:

```
# Path to the agents/ registry directory. Set explicitly in the image; locally
# it is discovered by walking up for pyproject.toml + agents/registry.yaml.
# SDLC_AGENTS_DIR=/app/agents
```

- [ ] **Step 12: Prove a non-editable install can find the registry**

This is the test that would have caught the live bug. Create `tests/test_registry_packaging.py`:

```python
"""A NON-editable install must find the registry.

The local install is editable (__editable__.ai_sdlc_temporal-0.1.0.pth), so
sdlc resolves to src/sdlc and any __file__-relative walk lands on the repo
root by accident. `pip install .` puts the package in site-packages, where
that accident does not happen — which is why the image could not boot. Slow
(builds a venv); marked so it can be deselected.
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.slow
def test_non_editable_install_resolves_registry_via_env(tmp_path):
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    py = venv / ("Scripts/python.exe" if sys.platform == "win32"
                 else "bin/python")
    subprocess.run([str(py), "-m", "pip", "install", "-q", str(REPO)],
                   check=True)

    probe = "from sdlc.agents.loader import load_registry; load_registry()"
    # cwd=tmp_path: OUTSIDE the repo, so discovery cannot rescue us and only
    # SDLC_AGENTS_DIR can work.
    done = subprocess.run(
        [str(py), "-c", probe], cwd=tmp_path, capture_output=True, text=True,
        env={"SDLC_AGENTS_DIR": str(REPO / "agents"), "PATH": ""},
    )
    assert done.returncode == 0, done.stderr


@pytest.mark.slow
def test_non_editable_install_without_env_fails_closed(tmp_path):
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    py = venv / ("Scripts/python.exe" if sys.platform == "win32"
                 else "bin/python")
    subprocess.run([str(py), "-m", "pip", "install", "-q", str(REPO)],
                   check=True)

    probe = "from sdlc.agents.loader import load_registry; load_registry()"
    done = subprocess.run([str(py), "-c", probe], cwd=tmp_path,
                          capture_output=True, text=True, env={"PATH": ""})
    assert done.returncode != 0
    assert "SDLC_AGENTS_DIR" in done.stderr        # names the mechanism
    assert "FileNotFoundError" not in done.stderr  # fails closed, deliberately
```

Register the marker in `pyproject.toml` under `[tool.pytest.ini_options]`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
markers = ["slow: builds a venv or otherwise takes >10s"]
```

- [ ] **Step 13: Run the packaging tests**

Run: `python -m pytest tests/test_registry_packaging.py -v -m slow`
Expected: 2 passed (takes ~30-60s)

If `pip install .` fails inside the venv for an unrelated reason (no network for dependencies), fall back to the source-inspection test named in the spec — and record in the commit message that you did, because it is the weaker proof:

```python
def test_dockerfile_ships_the_registry():
    text = (REPO / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY agents ./agents" in text
    assert "ENV SDLC_AGENTS_DIR=" in text
```

- [ ] **Step 14: Run the full suite**

Run: `python -m pytest`
Expected: 353 passed + the new tests, 0 failed. `PROMPT_SHAS` untouched in this task.

- [ ] **Step 15: Commit**

```bash
git add agents src/sdlc/agents/loader.py src/sdlc/models.py Dockerfile .env.example \
        tests/test_agents_registry.py tests/test_registry_resolution.py \
        tests/test_registry_packaging.py pyproject.toml
git rm -r --cached config 2>/dev/null || true
git commit -m "feat(registry): agents/<role>/ directories replace config/agents.yaml (E-1)

The directory name is the role name. validate_registry is re-fed the same
dict, not re-implemented: REQUIRED_ROLES first, then ADR-6 against dev, then
the mirror check, all unchanged.

Also deletes the parents[3] path walk, which was a live bug: Dockerfile never
COPYs config/, so DEFAULT_AGENTS_CONFIG resolved to
/usr/local/lib/python3.13/config/agents.yaml in the image and the worker died
at import. The editable install masked it locally -- parents[3] happened to
land on the repo root. Resolution is now explicit arg -> \$SDLC_AGENTS_DIR ->
repo-root discovery by marker files -> a RegistryError naming all three.

SDLC_AGENTS_CONFIG is renamed to SDLC_AGENTS_DIR because its meaning changed
from a file to a directory; the old name raises rather than being ignored.

KNOWN_ROLES = REQUIRED_ROLES | OPTIONAL_ROLES adds the seam an optional role
needs to be a known directory without weakening the fail-closed check.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Prompts become `instructions.md`

Moves eight prompt constants into their role folders. The hashes must not move — that is the whole test.

**Files:**
- Create: `agents/{clarify,architect,planner,qa,reviewer,analyst,merge_verdict,devops_planner}/instructions.md` (8 files)
- Modify: `src/sdlc/models.py:301-313` (`RoleConfig`)
- Modify: `src/sdlc/agents/loader.py` (`_parse_role`)
- Modify: `src/sdlc/agents/roles.py:54-149` (delete constants), `:235-249` (`_STAGE_PROMPTS`)
- Modify: `tests/conftest.py` (`write_registry_dir` must now emit `instructions.md`)
- Test: `tests/test_prompt_migration.py` (new)

**Interfaces:**
- Consumes: `KNOWN_ROLES`, `_parse_role`, `RoleConfig` from Task 1; `STAGE_ROLES` (`roles.py:218`); `write_registry_dir` (`tests/conftest.py`, Task 1).
- Produces: `RoleConfig.instructions: str | None` — the loaded `instructions.md` text, `None` for harness roles.

- [ ] **Step 1: Pin the hashes BEFORE anything moves**

These are the real values at HEAD. Create `tests/test_prompt_migration.py`:

```python
"""PROMPT_SHAS must be byte-identical across the instructions.md migration.

E-2 moves prompt bytes from Python constants into files. Per the registry
spec's finding 1 that buys no memoization capability -- the hash is over the
same bytes -- so the ONLY way this migration can be wrong is if a prompt
changed while moving. These literals were computed from roles.py before the
constants were deleted. A diff here is a migration bug, never an improvement.
"""
import hashlib

from sdlc.agents.roles import PROMPT_SHAS, REGISTRY, STAGE_ROLES

PRE_MIGRATION_SHAS = {
    "clarify": "f40fbf6ef7451def3717c0270315e5d3c3897ba288cf96a06daec064454e0560",
    "architect": "a7ca1e578f2db831689208eb1d1f965e3d42f7adbbafc132d095905715fd9fc6",
    "plan": "ffe6717f887ca9d6f7f6f7276b3d0a688a8dc7c76d17d1ef0e06bae4c470563e",
    "devops": "9d18988b3d1180ed20e93748bb93559bb6c1cb645606eebcdde212d12d866e57",
    "review": "dcaa8df20374b514a5ac329bef9ac1c42d4e03fe6b264f2496ecb41c6fd635f3",
    "analyze": "16c37dbf71d1d83800f9904ac835e62b91439066b0d235eb7a274531ec2f71b3",
    "qa": "f3a65764d65ec2f4c9b46fdb5ab404a414df9edaf579ec729145b173689a6179",
    "merge_verdict": "a63d593b33ad800bd2251de9c31482315094aea978e41aa306ba759234614c6c",
}


def test_prompt_shas_did_not_move():
    assert PROMPT_SHAS == PRE_MIGRATION_SHAS


def test_every_proposer_role_has_instructions():
    for role in set(STAGE_ROLES.values()):
        assert REGISTRY[role].instructions, f"{role} has no instructions"


def test_harness_roles_have_no_instructions():
    for role in ("dev", "test", "devops"):
        assert REGISTRY[role].instructions is None


def test_crlf_and_lf_instructions_hash_identically(tmp_path):
    """git autocrlf checks these files out with CRLF on Windows. The loader
    reads with universal newlines so the hash is over LF either way -- if that
    ever stops being true, PROMPT_SHAS moves on Windows only, which is a
    miserable bug to find. Pin it."""
    lf = tmp_path / "lf.md"
    crlf = tmp_path / "crlf.md"
    lf.write_bytes(b"line one\nline two")
    crlf.write_bytes(b"line one\r\nline two")
    assert (hashlib.sha256(lf.read_text(encoding="utf-8").encode()).hexdigest()
            == hashlib.sha256(crlf.read_text(encoding="utf-8").encode()).hexdigest())
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_prompt_migration.py -v`
Expected: FAIL — `ImportError: cannot import name 'REGISTRY'` is available but `RoleConfig` has no `instructions`; `test_every_proposer_role_has_instructions` fails with `AttributeError`.

- [ ] **Step 3: Add `instructions` to `RoleConfig`**

In `src/sdlc/models.py`, inside `class RoleConfig` after `model`:

```python
    # Loaded from agents/<role>/instructions.md by the registry loader (E-2).
    # None for harness roles: they run a CLI and carry no prompt of ours.
    # PROMPT_SHAS hashes these bytes, so editing one invalidates exactly that
    # stage's memo — which content_key already did via prompt_sha before the
    # text moved house. Moving it buys no new cache capability.
    instructions: str | None = None
```

- [ ] **Step 4: Generate the files from the constants**

Do **not** hand-copy. The constants are implicitly-concatenated string literals; a script guarantees byte-identity, which is the point of the pinned test.

```bash
ANTHROPIC_API_KEY=dummy python - <<'PY'
from pathlib import Path
import src.sdlc.agents.roles as r

for stage, text in r._STAGE_PROMPTS.items():
    role = r.STAGE_ROLES[stage]
    out = Path("agents") / role / "instructions.md"
    # write_bytes, never write_text: write_text would translate \n -> \r\n on
    # Windows and move the hash.
    out.write_bytes(text.encode("utf-8"))
    print(f"{stage:14s} -> {out}  ({len(text)} chars)")
PY
```

Expected output: 8 lines, `clarify -> agents/clarify/instructions.md (322 chars)` … `devops -> agents/devops_planner/instructions.md (193 chars)`.

Note: none of the prompts end with a newline, and these files must not either. Verify:

```bash
python -c "
from pathlib import Path
for p in sorted(Path('agents').glob('*/instructions.md')):
    b = p.read_bytes()
    assert not b.endswith(b'\n'), f'{p} has a trailing newline — the hash will move'
    print(f'{p}: {len(b)} bytes, no trailing newline')
"
```

- [ ] **Step 5: Load instructions in the loader**

In `src/sdlc/agents/loader.py`, extend `_parse_role` — replace its final `return RoleConfig(**data)`:

```python
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
    elif instructions_file.exists():
        raise RegistryError(
            f"role '{name}' is kind=harness and carries {instructions_file}, "
            f"which would never be read: silent dead config")
    return cfg
```

- [ ] **Step 6: Switch `PROMPT_SHAS` to the registry and delete the constants**

In `src/sdlc/agents/roles.py`, replace `_STAGE_PROMPTS` (lines ~235-243):

```python
# Prompt text now lives in agents/<role>/instructions.md (E-2). The hash is
# over the same bytes it was over when the text was a Python constant --
# tests/test_prompt_migration.py pins every value.
_STAGE_PROMPTS: dict[str, str] = {
    stage: REGISTRY[role].instructions for stage, role in STAGE_ROLES.items()
}
```

Delete the eight constants (`CLARIFY_PROMPT` through `DEVOPS_PROMPT`, lines ~54-149). Update each `Agent(...)`'s `system_prompt=` to read from the registry — e.g. for `clarify_agent`:

```python
clarify_agent = Agent(
    _model("clarify"),
    name="clarify_agent",
    output_type=ClarifiedRequirements,
    model_settings=MODEL_SETTINGS,
    system_prompt=REGISTRY["clarify"].instructions,
)
```

Do the same for the other seven, using each role's key: `architect`, `planner`, `qa`, `reviewer`, `analyst`, `merge_verdict`, `devops_planner`. **`qa_analyst_agent` uses `REGISTRY["qa"]` and `devops_agent` uses `REGISTRY["devops_planner"]`** — the role/agent name split. Task 3 removes these constructions entirely; they are updated here only to keep the suite green between tasks.

- [ ] **Step 7: Extend the shared helper — `instructions.md` is now mandatory**

Task 1's trees have no `instructions.md`, so every test built on `write_registry_dir` will now fail
with "missing instructions.md" — a reason unrelated to what those tests assert. Extend the helper in
`tests/conftest.py` rather than touching the tests:

```python
    for name in PROPOSER_ROLE_NAMES:
        d = root / name
        d.mkdir(exist_ok=True)
        (d / "agent.yaml").write_bytes(_PROPOSER_AGENT_YAML)
        (d / "instructions.md").write_bytes(b"do the thing")   # Task 2
```

- [ ] **Step 8: Run the migration tests**

Run: `python -m pytest tests/test_prompt_migration.py -v`
Expected: 4 passed. **If `test_prompt_shas_did_not_move` fails, a prompt changed during the move — fix the file, never the pinned literal.**

- [ ] **Step 9: Run the full suite**

Run: `python -m pytest`
Expected: all passed. Task 1's registry tests included — Step 7 is what keeps them green.

- [ ] **Step 10: Commit**

```bash
git add agents src/sdlc/models.py src/sdlc/agents/loader.py src/sdlc/agents/roles.py \
        tests/conftest.py tests/test_prompt_migration.py
git commit -m "feat(registry): prompts move to agents/<role>/instructions.md (E-2)

RoleConfig.instructions carries the loaded text; PROMPT_SHAS hashes those
bytes. Every hash is byte-identical to its pre-migration value, pinned as a
literal -- per the registry spec's finding 1 this buys no memoization
capability (content_key already took a prompt_sha over the same bytes), so a
moved hash could only mean a prompt changed during a move that promised not
to touch it.

Files generated from the constants by script, written as bytes: write_text
would translate \n -> \r\n on Windows and move every hash. A CRLF-vs-LF test
pins that a git autocrlf checkout still hashes as LF.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: `agent.py` per role

Distributes `Agent(...)` construction into the role folders. The risk is finding 7 — agent names are Temporal activity names — so the names get pinned before the move.

**Files:**
- Create: `agents/{clarify,architect,planner,qa,reviewer,analyst,merge_verdict,devops_planner}/agent.py` (8 files)
- Modify: `src/sdlc/agents/loader.py` (`_parse_role` validation, `build_agents`)
- Modify: `src/sdlc/agents/roles.py:150-215` (delete `Agent(...)` literals)
- Test: `tests/test_agent_folders.py` (new)

**Interfaces:**
- Consumes: `RoleConfig.instructions` (Task 2), `KNOWN_ROLES`, `load_registry`, `_resolve_agents_dir` (Task 1), `write_registry_dir` (`tests/conftest.py`), `MODEL_SETTINGS` (`roles.py:51`).
- Produces:
  - Each `agents/<role>/agent.py` exposes `build(model: str, instructions: str, model_settings: ModelSettings) -> Agent`.
  - `build_agents(roles: dict[str, RoleConfig], model_settings: ModelSettings, agents_dir: str | os.PathLike | None = None) -> dict[str, Agent]` in `loader.py` — keyed by **role** name.

**Two signature decisions, both load-bearing:**
- **`model_settings` is a required parameter, not read from `roles.py`.** `roles.py` imports
  `build_agents` from `loader`, so `loader` importing `MODEL_SETTINGS` back from `roles` is a cycle.
  It would happen to work — `MODEL_SETTINGS` is defined above the `build_agents(...)` call, so the
  partially-initialised module in `sys.modules` already has it — and "happens to work because of
  definition order" is how the registry spec's finding 3 was born. Pass it in.
- **`agents_dir` is a parameter, not re-resolved.** `load_registry(tmp)` then
  `build_agents(roles)` would import `agent.py` from the *shipped* registry while validating a tmp
  one. The caller knows which tree it loaded; make it say so.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agent_folders.py`:

```python
"""agent.py per role — eve's agent.ts, in Python.

Two invariants, both easy to break and expensive to notice:
  * agent NAMES are Temporal activity names ("never rename after deploying to
    production"), and role name != agent name for two roles.
  * dynamic imports must not run before validation, or the registry spec's
    finding 3 comes back through a new door.
"""
import pytest

from sdlc.agents.loader import RegistryError, build_agents, load_registry
from sdlc.agents.roles import MODEL_SETTINGS
from tests.conftest import write_registry_dir

# roles.py at HEAD, verified. NOT derived from the role name: 'qa' builds
# qa_analyst_agent and 'devops_planner' builds devops_agent.
PRE_MIGRATION_AGENT_NAMES = {
    "clarify": "clarify_agent",
    "architect": "architect_agent",
    "planner": "planner_agent",
    "qa": "qa_analyst_agent",
    "reviewer": "reviewer_agent",
    "analyst": "analyst_agent",
    "merge_verdict": "merge_verdict_agent",
    "devops_planner": "devops_agent",
}


def test_agent_names_did_not_move():
    """A renamed agent is a renamed Temporal activity — a production break no
    other test in this suite would surface."""
    agents = build_agents(load_registry(), MODEL_SETTINGS)
    assert {r: a.name for r, a in agents.items()} == PRE_MIGRATION_AGENT_NAMES


def test_harness_roles_build_no_agent():
    agents = build_agents(load_registry(), MODEL_SETTINGS)
    for role in ("dev", "test", "devops"):
        assert role not in agents


def test_proposer_missing_agent_py_rejected(tmp_path):
    root = write_registry_dir(tmp_path / "agents")
    (root / "reviewer" / "agent.py").unlink()
    with pytest.raises(RegistryError, match="reviewer"):
        load_registry(root)


def test_agent_py_without_build_rejected(tmp_path):
    root = write_registry_dir(tmp_path / "agents")
    (root / "reviewer" / "agent.py").write_bytes(b"x = 1\n")
    roles = load_registry(root)          # structural check is at build time
    with pytest.raises(RegistryError, match="build"):
        build_agents(roles, MODEL_SETTINGS, agents_dir=root)


def test_duplicate_agent_names_rejected(tmp_path):
    """Only reachable now that construction is distributed across files."""
    root = write_registry_dir(tmp_path / "agents")
    (root / "analyst" / "agent.py").write_bytes(
        _AGENT_PY.format(name="reviewer_agent").encode())   # steals the name
    roles = load_registry(root)
    with pytest.raises(RegistryError, match="reviewer_agent"):
        build_agents(roles, MODEL_SETTINGS, agents_dir=root)


def test_validation_precedes_import(tmp_path):
    """An ADR-6-violating tree whose agent.py would explode on import must
    fail with RegistryError from validation, not with the import error.
    Asserts the ORDERING, not just the outcome — if build_agents ever creeps
    inside load_registry, this is what catches it."""
    root = write_registry_dir(tmp_path / "agents")
    (root / "reviewer" / "agent.yaml").write_bytes(
        b"kind: proposer\nmodel: zai-coding-plan/other\n")     # dev's family
    for role in ("clarify", "architect"):
        (root / role / "agent.py").write_bytes(
            b"raise RuntimeError('this module must never be imported')\n")
    with pytest.raises(RegistryError, match="family"):
        load_registry(root)
```

`_AGENT_PY` is the template the conftest helper uses; import it alongside `write_registry_dir`.

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/test_agent_folders.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_agents'`

- [ ] **Step 3: Extend the shared helper — `agent.py` is now mandatory**

Same reason as Task 2 Step 7: without this, every tree built by `write_registry_dir` fails for
"missing agent.py" and Tasks 1–2's tests break for an unrelated reason. In `tests/conftest.py`:

```python
_AGENT_PY = (
    "from pydantic_ai import Agent\n"
    "def build(model, instructions, model_settings):\n"
    "    return Agent(model, name={name!r}, model_settings=model_settings,\n"
    "                 system_prompt=instructions)\n"
)

# Role -> agent name. Mirrors roles.py; NOT derived — 'qa' builds
# qa_analyst_agent, 'devops_planner' builds devops_agent.
_TEST_AGENT_NAMES = {
    "clarify": "clarify_agent", "architect": "architect_agent",
    "planner": "planner_agent", "qa": "qa_analyst_agent",
    "reviewer": "reviewer_agent", "analyst": "analyst_agent",
    "merge_verdict": "merge_verdict_agent", "devops_planner": "devops_agent",
}
```

and inside the proposer loop:

```python
        (d / "agent.py").write_bytes(
            _AGENT_PY.format(name=_TEST_AGENT_NAMES[name]).encode())  # Task 3
```

- [ ] **Step 4: Write the eight `agent.py` files**

`agents/clarify/agent.py`:

```python
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from sdlc.models import ClarifiedRequirements


def build(model: str, instructions: str,
          model_settings: ModelSettings) -> Agent:
    return Agent(
        model,
        name="clarify_agent",       # Temporal activity name — NEVER rename
        output_type=ClarifiedRequirements,
        model_settings=model_settings,
        system_prompt=instructions,
    )
```

`agents/architect/agent.py` — identical but `name="architect_agent"`, `output_type=ArchitectureSpec`.
`agents/planner/agent.py` — `name="planner_agent"`, `output_type=ImplementationPlan`.
`agents/qa/agent.py` — `name="qa_analyst_agent"`, `output_type=QAReport`.
`agents/reviewer/agent.py` — `name="reviewer_agent"`, `output_type=ReviewReport`.
`agents/analyst/agent.py` — `name="analyst_agent"`, `output_type=AnalysisReport`.
`agents/merge_verdict/agent.py` — `name="merge_verdict_agent"`, `output_type=MergeVerdict`.
`agents/devops_planner/agent.py` — `name="devops_agent"`, `output_type=ImplementationPlan` (devops tasks reuse the task shape).

Each imports its `output_type` from `sdlc.models`. Nothing else changes between them.

- [ ] **Step 5: Add `build_agents` and the `agent.py` structural checks**

In `src/sdlc/agents/loader.py`, add to `_parse_role`'s proposer branch (after the `instructions.md` checks):

```python
        if not (d / "agent.py").is_file():
            raise RegistryError(f"role '{name}': missing {d / 'agent.py'}")
```

And in the harness branch, alongside the `instructions.md` check:

```python
    elif instructions_file.exists() or (d / "agent.py").exists():
        raise RegistryError(
            f"role '{name}' is kind=harness and carries instructions.md or "
            f"agent.py, which would never be read: silent dead config")
```

Then append to the module:

```python
import importlib.util
from typing import TYPE_CHECKING

if TYPE_CHECKING:                       # pydantic_ai import is not free
    from pydantic_ai import Agent


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
        agent = _load_build(name, root / name)(cfg.model, cfg.instructions,
                                               model_settings)
        if agent.name in seen:
            raise RegistryError(
                f"roles '{seen[agent.name]}' and '{name}' both build an agent "
                f"named '{agent.name}': colliding Temporal activity names")
        seen[agent.name] = name
        agents[name] = agent
    return agents
```

- [ ] **Step 6: Run the folder tests**

Run: `python -m pytest tests/test_agent_folders.py -v`
Expected: 5 passed. **If `test_agent_names_did_not_move` fails, fix the `agent.py`, never the pinned map.**

- [ ] **Step 7: Rewire `roles.py`**

Replace the eight `Agent(...)` constructions (lines ~150-215) with:

```python
AGENTS = build_agents(REGISTRY)

# Module-level names are preserved verbatim: feature.py and worker.py import
# these and must not change. Note role name != agent name for two of them.
clarify_agent = AGENTS["clarify"]
architect_agent = AGENTS["architect"]
planner_agent = AGENTS["planner"]
qa_analyst_agent = AGENTS["qa"]                 # role 'qa'
reviewer_agent = AGENTS["reviewer"]
analyst_agent = AGENTS["analyst"]
merge_verdict_agent = AGENTS["merge_verdict"]
devops_agent = AGENTS["devops_planner"]         # role 'devops_planner'
```

Add `build_agents` to the existing `from .loader import load_registry` import. The `Agent` import from `pydantic_ai` and the `output_type` imports from `..models` become unused in `roles.py` — delete them. `MODEL_SETTINGS`, `STAGE_ROLES`, `STAGE_MODELS`, `PROMPT_SHAS`, every `t_*` and `ALL_TEMPORAL_AGENTS` are unchanged.

- [ ] **Step 8: Run the full suite**

Run: `python -m pytest`
Expected: all passed, including `tests/test_factory_purity.py`.

If purity fails: `feature.py` imports `roles` inside `workflow.unsafe.imports_passed_through()`, and the dynamic imports run under it, so this should hold. If it does not, the fallback named in the spec is building agents at worker boot rather than at `roles.py` import — take that on evidence, and report before doing it, since it changes what `roles.py` exports.

- [ ] **Step 9: Verify the worker still boots**

Run: `ANTHROPIC_API_KEY=dummy python -c "import sdlc.worker; print('worker imports OK')"`
Expected: `worker imports OK`

- [ ] **Step 10: Commit**

```bash
git add agents src/sdlc/agents/loader.py src/sdlc/agents/roles.py \
        tests/conftest.py tests/test_agent_folders.py
git commit -m "feat(registry): agent.py per role — the directory is the role (E-1)

Each proposer folder exposes build(model, instructions, model_settings).
agent.py declares the role's SHAPE (name, output_type); the loader supplies
its CONFIGURATION as arguments. An agent.py that opens a file has crossed the
line: assets are what you edit to change behaviour, code is what makes them
work.

Agent names are pinned as literals before the move. They are Temporal activity
names -- 'never rename after deploying to production' -- and role name is not
agent name: 'qa' builds qa_analyst_agent, 'devops_planner' builds
devops_agent. A renamed agent is a production break no other test would
surface.

Validation precedes import: build_agents runs only after load_registry has
returned, so an ADR-6-violating registry fails before any agent.py is
imported. A test asserts the ordering, not just the outcome -- otherwise the
registry spec's finding 3 comes back through a new door.

Modules load by file path under _sdlc_agent_<role>, so the registry root
agents/ never resolves against the code package src/sdlc/agents/.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Roadmap amendments

**Files:**
- Modify: `ROADMAP.md` §7, §9.1, §9.7

- [ ] **Step 1: Update the tracker**

In `ROADMAP.md` §9.1, mark E-1 and E-2 `[x]` and record *why* they were revived:

```markdown
- [x] **E-1** `agents/<role>/` directory loader — `load_registry()` walks a directory
  (`agent.yaml` + `instructions.md` + `agent.py`) instead of parsing one file. ADR-6's
  family-inequality check keeps biting at boot, unchanged: `validate_registry` is re-fed the
  same dict, not re-implemented. Also deleted the `parents[3]` walk, which made the
  containerised worker unbootable (the editable install masked it). Spec:
  `docs/superpowers/specs/2026-07-17-agents-as-folders-design.md`.
- [x] **E-2** Prompts moved to `agents/<role>/instructions.md`; `PROMPT_SHAS` derives from file
  content. Every hash byte-identical, pinned. *Revived not by the memoization argument E-3's
  note made — finding 1 checked that and it was wrong — but because the research role is the
  first role a folder describes rather than decorates, and a folder for it beside eleven YAML
  entries would reopen the two-registry hole.*
```

In §9.1 E-4, delete "Blocked on E-2."

In §7, mark the prompts-as-assets item done for its first clause:

```markdown
- [ ] ⚠️ `prompts/` as versioned assets — prompts now live in `agents/<role>/instructions.md`
  and hash into `PROMPT_SHAS` from file content (E-2 ✅). The "**with an eval loop**" clause
  stays open on E-4.
```

In §9.7, replace ordering item 2 with a note that E-1/E-2 landed and E-3 was subsumed by the registry increment.

- [ ] **Step 2: Commit**

```bash
git add ROADMAP.md
git commit -m "docs(roadmap): E-1/E-2 land; agents are folders

Records the revival reason: not E-3's memoization argument (finding 1 checked
it and it was wrong) but the research role being the first role a folder
describes rather than decorates.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Not in this plan

- **`tools/` discovery** — no role has tools until research does. That loader clause belongs to `2026-07-17-research-agent-grounded-briefs-design.md`.
- **`kind: research`, `RoleConfig.provider`** — same.
- **Populating `OPTIONAL_ROLES`** — it ships empty and named. The research spec adds its one entry.
- **E-4's eval loop** — unblocked by Task 2, not delivered by it.
- **Editing what any prompt says** — Task 2's pinned hashes exist to make that impossible here.
