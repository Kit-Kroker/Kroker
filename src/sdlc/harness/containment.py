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

import fnmatch
import hashlib
import json
import os
import re
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, Field

from ..models import ContainmentLayer, ToolGrant

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


class Action(str, Enum):
    """What a matched rule does. DENY is E-16's behaviour and the default;
    ESCALATE raises a human gate through FR-301/FR-302 (E-17)."""
    DENY = "deny"
    ESCALATE = "escalate"


class Rule(BaseModel):
    id: str
    layer: ContainmentLayer      # MINIMUM capability required (spec §4a)
    action: Action = Action.DENY   # E-17; DENY keeps every E-16 rule as-is
    tools: list[str]
    predicate: Predicate
    reason: str
    patterns: list[str] = Field(default_factory=list)
    allow_hosts: list[str] = Field(default_factory=list)


class Policy(BaseModel):
    version: int
    rules: list[Rule] = Field(default_factory=list)
    # Absolute path the asset was loaded from (None for hand-built policies).
    # The hook needs it: claude runs the hook with cwd = the task worktree
    # (a temp dir), so the hook's own discovery would fail — the adapter
    # forwards this path as `--policy` to make the hook cwd-independent.
    source_path: Path | None = None


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
            if (rules[-1].action is Action.ESCALATE
                    and rules[-1].layer is ContainmentLayer.NATIVE):
                raise ContainmentError(
                    f"rule {rid!r} in {p} sets action: escalate with layer: "
                    f"native. A native `permissions.deny` strictly beats a hook "
                    f"allow, so an approved call would still be blocked — the "
                    f"gate would be theatre. Escalating rules must be layer: hook.")
        except Exception as e:                    # noqa: BLE001 - re-typed
            raise ContainmentError(
                f"invalid rule {rid!r} in {p}: {e}") from e
    return Policy(version=version, rules=rules, source_path=p.resolve())


class Verdict(BaseModel):
    allow: bool
    rule_id: str | None = None
    reason: str | None = None
    action: Action = Action.DENY   # the matched rule's action; DENY when allowed


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


def host_allowed(host: str, allow_hosts: list[str]) -> bool:
    """Exact match or subdomain of an allowlisted host.

    Public because E-9's WebhookNotifier reuses it: two implementations of
    this rule would drift, and a host allowed for WebFetch but denied for a
    notification (or the reverse) is a policy hole.
    """
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
        return any(not host_allowed(h, rule.allow_hosts) for h in hosts)

    return False


def evaluate(policy: Policy, tool: str, tool_input: dict,
             worktree: str) -> Verdict:
    """First matching rule wins. `worktree` is a PARAMETER, never computed:
    create_worktree may return <task>.N after a Windows lock fallback and its
    returned path is authoritative (activities.py:260-274)."""
    for rule in policy.rules:
        if _rule_denies(rule, tool, tool_input, worktree):
            return Verdict(allow=False, rule_id=rule.id, reason=rule.reason,
                           action=rule.action)
    return Verdict(allow=True)


# The hook writes this marker into the reason string after the `[rule-id] `
# prefix when it matched an ESCALATE rule but could not escalate. Both the
# hook (writer) and the adapter (reader) import it from here so the two can
# never drift apart.
ESCALATION_UNAVAILABLE = "escalation unavailable"


def is_declined_reason(text: str) -> bool:
    """True when a denial reason says an escalation was declined, not that a
    rule simply denies. The rule-id prefix has already been stripped."""
    return text.startswith(ESCALATION_UNAVAILABLE)


def digest_tool_input(tool_input: dict) -> str:
    """Canonical digest of a tool call's input. Used by BOTH the activity
    (building a grant) and the hook (matching one), so canonicalisation can
    never disagree between them."""
    canonical = json.dumps(tool_input, sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False,
                           default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def match_grant(grants: list[ToolGrant], tool: str, tool_use_id: str,
                tool_input: dict) -> ToolGrant | None:
    """The grant for exactly this call, or None. All three of tool name,
    tool_use_id and input digest must agree — the id gives single-use (the
    CLI replays the original id; a new call gets a new one) and the digest
    guards against id reuse carrying a different payload."""
    if not tool_use_id:
        return None
    digest = digest_tool_input(tool_input)
    for g in grants:
        if (g.tool_use_id == tool_use_id and g.tool == tool
                and g.input_digest == digest):
            return g
    return None


def load_grants(path: str | os.PathLike | None) -> list[ToolGrant]:
    """Read the grants asset the adapter wrote. A missing path or file means
    'no decision yet', which makes an escalate rule escalate — the safe
    direction. Malformed content raises: a grants file we cannot parse must
    not silently become 'no grants', which would re-ask a decided call."""
    if path is None:
        return []
    p = Path(path)
    if not p.is_file():
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    return [ToolGrant.model_validate(e) for e in raw]
