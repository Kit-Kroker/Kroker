"""C2 Task 2: the same G, compiled by every engine, must select the same files.

The failure this file exists to catch: a pattern that is PRESENT in an
engine's output but MATCHES NOTHING there. Presence assertions ("the freeze
pattern is in the deny list") sail straight past it. Every assertion here
evaluates a TARGET.
"""

from __future__ import annotations

import fnmatch
import json
import subprocess
from pathlib import Path

import pytest

from sdlc.harness.base import HarnessRequest
from sdlc.harness.claude_code import ClaudeCodeHarness
from sdlc.harness.containment import (
    Action,
    Phase,
    Policy,
    Predicate,
    Rule,
    evaluate,
    repair_patterns,
)
from sdlc.harness.models import ContainmentLayer
from sdlc.harness.opencode import OpenCodeHarness

# The three probe shapes. The ROOT-FILENAME probe is the one that catches
# the `**/`-prefix trap: `**/conftest.py` matches tests/unit/conftest.py but
# NOT a repo-root conftest.py, in git's pathspec AND in fnmatch alike.
NESTED_REL = "tests/unit/test_auth.py"
NESTED_ABS = "/wt/tests/unit/test_auth.py"
ROOT_REL = "conftest.py"


def _policy() -> Policy:
    return Policy(
        version=1,
        rules=[
            Rule(
                id="no-test-edit-during-repair",
                layer=ContainmentLayer.NATIVE,
                action=Action.DENY,
                phase=Phase.REPAIR,
                tools=["Write", "Edit", "NotebookEdit"],
                predicate=Predicate.PATH_MATCHES,
                patterns=["tests/**", "**/tests/**", "conftest.py", "**/conftest.py"],
                reason="Tests are frozen during repair.",
            )
        ],
    )


@pytest.mark.parametrize("target", [NESTED_REL, NESTED_ABS, ROOT_REL])
def test_hook_engine_denies_every_probe_shape_during_repair(target):
    """Engine 1: fnmatch, via evaluate(). All three shapes must be covered
    by the paired pattern forms."""
    v = evaluate(_policy(), "Write", {"file_path": target}, "/wt", repair=True)
    assert v.allow is False, f"{target} escaped the fence"


@pytest.mark.parametrize("target", [NESTED_REL, NESTED_ABS, ROOT_REL])
def test_hook_engine_allows_every_probe_shape_on_pass_one(target):
    v = evaluate(_policy(), "Write", {"file_path": target}, "/wt", repair=False)
    assert v.allow is True


@pytest.mark.parametrize("target", [NESTED_REL, NESTED_ABS, ROOT_REL])
def test_claude_native_deny_globs_select_every_probe_shape(target):
    """Engine 2: claude's `Tool(pattern)` deny syntax. We cannot run claude
    here, so evaluate the PATTERN half of each emitted entry with the same
    glob semantics claude applies, and assert a match."""
    h = ClaudeCodeHarness()
    req = HarnessRequest(prompt="p", cwd="/wt", repair=True)
    h.apply_containment(_policy(), req)
    settings = json.loads(Path(_settings_path(req)).read_text(encoding="utf-8"))
    deny = settings["permissions"]["deny"]
    pats = [e[e.index("(") + 1 : -1] for e in deny if e.startswith("Write(")]
    assert any(fnmatch.fnmatch(target, p) for p in pats), f"{target} matched none of {pats}"


def test_claude_emits_no_freeze_rule_on_pass_one():
    h = ClaudeCodeHarness()
    req = HarnessRequest(prompt="p", cwd="/wt", repair=False)
    h.apply_containment(_policy(), req)
    settings = json.loads(Path(_settings_path(req)).read_text(encoding="utf-8"))
    assert settings["permissions"]["deny"] == []
    # And the hook matcher must be empty too, so pass 1 spawns no hook at all.
    assert settings["hooks"]["PreToolUse"] == []


def test_claude_hook_command_carries_repair_only_during_repair():
    h = ClaudeCodeHarness()
    for repair in (True, False):
        req = HarnessRequest(prompt="p", cwd="/wt", repair=repair)
        h.apply_containment(_policy(), req)
        settings = json.loads(Path(_settings_path(req)).read_text(encoding="utf-8"))
        hooks = settings["hooks"]["PreToolUse"]
        if repair:
            assert "--repair" in hooks[0]["hooks"][0]["command"]
        else:
            assert hooks == []


def _settings_path(req: HarnessRequest) -> str:
    """The tempfile path apply_containment appended as `--settings <path>`."""
    return req.extra_args[req.extra_args.index("--settings") + 1]


@pytest.mark.parametrize("target", [NESTED_REL, ROOT_REL])
def test_opencode_edit_bucket_selects_every_relative_probe(tmp_path, target):
    """Engine 3: opencode's permission.edit globs. opencode resolves paths
    relative to the worktree, so the absolute probe does not apply here."""
    h = OpenCodeHarness()
    req = HarnessRequest(prompt="p", cwd=str(tmp_path), repair=True)
    h.apply_containment(_policy(), req)
    doc = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    pats = [p for p, v in doc["permission"]["edit"].items() if v == "deny"]
    assert any(fnmatch.fnmatch(target, p) for p in pats), f"{target} matched none of {pats}"


def test_opencode_thaw_removes_the_freeze_it_added(tmp_path):
    """The defect this exists for: opencode's merge is append-only, so
    without owned-key bookkeeping the freeze RATCHETS and a human thaw
    silently fails on this harness."""
    h = OpenCodeHarness()
    cfg = tmp_path / "opencode.json"

    # attempt 2: frozen
    h.apply_containment(_policy(), HarnessRequest(prompt="p", cwd=str(tmp_path), repair=True))
    frozen = json.loads(cfg.read_text(encoding="utf-8"))["permission"]["edit"]
    assert "tests/**" in frozen

    # attempt 3: THAWED -- the freeze keys must be gone from the file on disk
    h.apply_containment(_policy(), HarnessRequest(prompt="p", cwd=str(tmp_path), repair=False))
    thawed = json.loads(cfg.read_text(encoding="utf-8"))["permission"]["edit"]
    assert "tests/**" not in thawed
    assert "conftest.py" not in thawed


def test_opencode_preserves_repo_authored_permission_keys_across_freeze_and_thaw(tmp_path):
    cfg = tmp_path / "opencode.json"
    cfg.write_text(
        json.dumps({"permission": {"edit": {"secrets/**": "deny"}}, "plugin": ["x"]}),
        encoding="utf-8",
    )
    h = OpenCodeHarness()
    h.apply_containment(_policy(), HarnessRequest(prompt="p", cwd=str(tmp_path), repair=True))
    h.apply_containment(_policy(), HarnessRequest(prompt="p", cwd=str(tmp_path), repair=False))
    doc = json.loads(cfg.read_text(encoding="utf-8"))
    assert doc["permission"]["edit"]["secrets/**"] == "deny"  # repo key survives both
    assert doc["plugin"] == ["x"]  # unrelated config survives


def test_opencode_removal_is_scoped_to_the_edit_bucket(tmp_path):
    """G is PATH_MATCHES -> `edit`. A same-named key in `bash` is not ours."""
    cfg = tmp_path / "opencode.json"
    cfg.write_text(json.dumps({"permission": {"bash": {"tests/**": "deny"}}}), encoding="utf-8")
    h = OpenCodeHarness()
    h.apply_containment(_policy(), HarnessRequest(prompt="p", cwd=str(tmp_path), repair=False))
    doc = json.loads(cfg.read_text(encoding="utf-8"))
    assert doc["permission"]["bash"]["tests/**"] == "deny"


@pytest.mark.parametrize("target", [NESTED_REL, ROOT_REL])
def test_git_pathspec_selects_every_relative_probe(tmp_path, target):
    """Engine 4: git pathspec, used by the drift backstop. MEASURED, not
    assumed: git's DEFAULT pathspec agrees with fnmatch on these forms;
    `:(glob)` does NOT, which is why the backstop must never use it."""
    repo = tmp_path / "r"
    (repo / "tests" / "unit").mkdir(parents=True)

    def run(*a: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True, text=True)

    subprocess.run(["git", "init", "-q", "."], cwd=repo, check=True)
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    for f in (NESTED_REL, ROOT_REL):
        (repo / f).write_text("x\n", encoding="utf-8")
    run("add", "-A")
    run("commit", "-qm", "base")
    anchor = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    (repo / target).write_text("WEAKENED\n", encoding="utf-8")

    pats = repair_patterns(_policy())
    out = subprocess.run(
        ["git", "diff", "--name-only", anchor, "--", *pats],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert target in out, f"{target} invisible to the git dialect via {pats}"


# --- Task 3: the rule that actually ships ----------------------------------


def test_shipped_policy_freezes_every_probe_shape_during_repair():
    """The rule that actually ships must pass the same probes as the fixture.

    A fixture-only guarantee is worthless: the fixture is not what runs."""
    from sdlc.harness.containment import load_policy

    policy = load_policy(Path(__file__).resolve().parents[1] / "policy" / "containment.yaml")
    for target in (NESTED_REL, NESTED_ABS, ROOT_REL, "/wt/conftest.py", "src/util_test.go"):
        assert (
            evaluate(policy, "Write", {"file_path": target}, "/wt", repair=True).allow is False
        ), f"shipped policy lets {target} through during repair"
        assert (
            evaluate(policy, "Write", {"file_path": target}, "/wt", repair=False).allow is True
        ), f"shipped policy blocks {target} on the FREE first pass"


def test_shipped_policy_does_not_list_bash_on_the_freeze_rule():
    """PATH_MATCHES can never fire on Bash -- target_of returns the COMMAND
    string for it. Listing Bash would be dead code that reads like coverage.
    The Bash channel belongs to the drift backstop."""
    from sdlc.harness.containment import load_policy

    policy = load_policy(Path(__file__).resolve().parents[1] / "policy" / "containment.yaml")
    freeze = next(r for r in policy.rules if r.id == "no-test-edit-during-repair")
    assert "Bash" not in freeze.tools


def test_shipped_policy_drift_set_covers_test_config():
    from sdlc.harness.containment import drift_globs, load_policy

    policy = load_policy(Path(__file__).resolve().parents[1] / "policy" / "containment.yaml")
    d = drift_globs(policy)
    for expected in ("pyproject.toml", "pytest.ini", "tests/**", "requirements.txt"):
        assert expected in d, f"{expected} missing from the drift set D"
