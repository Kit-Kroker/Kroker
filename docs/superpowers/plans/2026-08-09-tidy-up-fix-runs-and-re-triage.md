# E-44 — Tidy-Up Fix Runs and Re-Triage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn accepted `MECHANICAL` triage findings into governed brownfield `FeatureWorkflow` child runs — one PR each — then re-triage a composite verification branch and record the before/after delta.

**Architecture:** A new `TidyUpWorkflow` (a `GateHost`, like `TriageWorkflow`) orchestrates: baseline triage → backlog → `tidy_up` gate → N seeded fix runs → verification branch → after-triage → delta. `FeatureWorkflow` gains one optional `SeededWork` input that supplies a deterministically-authored `ArchitectureSpec` + `ImplementationPlan` and skips stages 0–3; everything from `_dev_task` down is untouched. The delta is a pure function that never reads absence as resolution.

**Tech Stack:** Python 3.11+, Pydantic v2, Temporal (`temporalio`), pytest. Windows host — the Bash tool runs Git Bash; PowerShell is the primary shell.

**Spec:** `docs/superpowers/specs/2026-08-09-tidy-up-fix-runs-and-re-triage-design.md`. Decision ids (D1–D10) below refer to that document.

## Global Constraints

- **`src/sdlc/triage/models.py` and `src/sdlc/triage/delta.py` are pure.** They may import Pydantic, stdlib, `..measurement`, and each other. They must **never** import `models.py` (the root one), `activities.py`, or `temporalio`. A dependency there would appear as a reviewable import — this is stated in `triage/models.py`'s own module docstring.
- **`compute_delta` is the only producer of a `FindingState`**, exactly as `compute_readiness` is the only producer of a `Verdict` (E-41 D4). No caller sets a state.
- **A `Measurement` that is not `MEASURED` never becomes a zero or an absence.** FR-915.
- **No LLM call anywhere in `src/sdlc/triage/` or in `TidyUpWorkflow` itself.** The model calls all happen inside the child `FeatureWorkflow` runs.
- **Workflow child ids are derived, never generated** — replay must produce the same id. No `uuid`, no `workflow.random()` for ids.
- **Test markers:** `pytest` alone runs fast unit tests. Temporal tests need `pytest -m temporal` and carry `@pytest.mark.temporal`.
- **Commit trailer** on every commit:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  ```
- Existing behavior of the seven triage signals must keep passing: `pytest tests/ -k triage` is green before and after every task.

---

## File Structure

**Created:**

| File | Responsibility |
|---|---|
| `src/sdlc/triage/delta.py` | `FindingState`, `FindingDelta`, `compute_delta`. Pure. |
| `src/sdlc/tidyup/__init__.py` | Package marker. |
| `src/sdlc/tidyup/backlog.py` | Pure: mechanical-finding selection, `DevTask` authoring, `SeededWork` construction. |
| `src/sdlc/workflows/tidyup.py` | `TidyUpWorkflow`, `TidyUpInput`, `TidyUpReport`, `FixRunResult`. |
| `tests/test_triage_finding_identity.py` | Task 1 + 2 tests. |
| `tests/test_triage_delta.py` | Task 3 tests. |
| `tests/test_seeded_work.py` | Task 4 tests. |
| `tests/test_verification_branch.py` | Task 5 tests. |
| `tests/test_tidyup_backlog.py` | Task 6 tests. |
| `tests/test_tidyup_workflow.py` | Task 7 tests. |
| `tests/test_tidyup_cli_wiring.py` | Task 8 tests. |

**Modified:**

| File | Change |
|---|---|
| `src/sdlc/triage/models.py` | `TriageFinding.key`; `finding_identity`, `evidence_key`, `dedupe_by_identity`; `SignalResult._identities_unique`. |
| `src/sdlc/triage/signals/{secrets,misconfig,dependencies,outliers}.py` | `key=` at multi-firing call sites; dedupe; `VERSION` bump. |
| `src/sdlc/models.py` | `SeededWork`. |
| `src/sdlc/workflows/feature.py` | `run`/`_pipeline` accept `seeded: SeededWork | None`. |
| `src/sdlc/activities.py` | `VerifyBranchInput`, `VerifyResult`, `build_verification_branch`. |
| `src/sdlc/worker.py` | Register `TidyUpWorkflow` + `build_verification_branch`. |
| `src/sdlc/cli.py` | `sdlc tidyup` / `tidyup select` / `tidyup show`. |
| `ROADMAP.md` | Mark E-44, FR-904, US-8, US-9, P5. |

---

### Task 1: Finding identity primitives

**Files:**
- Modify: `src/sdlc/triage/models.py`
- Test: `tests/test_triage_finding_identity.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `TriageFinding.key: str`; `finding_identity(f: TriageFinding) -> str`; `evidence_key(text: str) -> str`; `dedupe_by_identity(findings: list[TriageFinding]) -> list[TriageFinding]`. Tasks 2, 3, 6 all import these from `sdlc.triage.models`.

The `SignalResult` validator is deliberately **not** in this task — landing it before Task 2 supplies the keys would break the existing signal suites.

- [ ] **Step 1: Write the failing test**

Create `tests/test_triage_finding_identity.py`:

```python
"""D3: identity is (signal, rule, path, key) and never `line`, which drifts
the moment a fix lands above the finding."""

from sdlc.triage.models import (
    FixClass,
    TriageFinding,
    dedupe_by_identity,
    evidence_key,
    finding_identity,
)


def _f(**kw):
    base = dict(
        signal="deps",
        rule="unpinned_dependency",
        severity="medium",
        detail="d",
        fix_class=FixClass.MECHANICAL,
    )
    base.update(kw)
    return TriageFinding(**base)


def test_key_defaults_to_empty():
    assert _f().key == ""


def test_identity_excludes_line():
    a = _f(path="requirements.txt", line=3, key="flask")
    b = _f(path="requirements.txt", line=41, key="flask")
    assert finding_identity(a) == finding_identity(b)


def test_identity_separates_two_findings_of_one_rule_in_one_file():
    a = _f(path="requirements.txt", key="flask")
    b = _f(path="requirements.txt", key="requests")
    assert finding_identity(a) != finding_identity(b)


def test_identity_separates_rules_and_paths_and_signals():
    base = _f(path="requirements.txt", key="flask")
    assert finding_identity(base) != finding_identity(_f(path="pyproject.toml", key="flask"))
    assert finding_identity(base) != finding_identity(
        _f(path="requirements.txt", rule="unused_dependency", key="flask")
    )
    assert finding_identity(base) != finding_identity(
        _f(path="requirements.txt", signal="other", key="flask")
    )


def test_evidence_key_is_stable_short_and_hides_the_text():
    secret = "AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'"
    k = evidence_key(secret)
    assert k == evidence_key(secret)
    assert len(k) == 12
    assert "AKIA" not in k


def test_evidence_key_separates_different_text():
    assert evidence_key("a = 1") != evidence_key("b = 2")


def test_evidence_key_survives_undecodable_bytes():
    """Signals read blobs that are not guaranteed to be clean UTF-8."""
    assert len(evidence_key("caf\udce9 = 1")) == 12


def test_dedupe_keeps_the_first_of_each_identity():
    a = _f(path="s.py", key="k", line=1)
    b = _f(path="s.py", key="k", line=9)
    c = _f(path="s.py", key="other", line=4)
    out = dedupe_by_identity([a, b, c])
    assert [f.line for f in out] == [1, 4]


def test_dedupe_preserves_order_and_returns_a_new_list():
    src = [_f(path="a", key="1"), _f(path="b", key="2")]
    out = dedupe_by_identity(src)
    assert out == src and out is not src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_triage_finding_identity.py -v`
Expected: FAIL — `ImportError: cannot import name 'finding_identity'`

- [ ] **Step 3: Write minimal implementation**

In `src/sdlc/triage/models.py`, add `import hashlib` to the stdlib imports at the top, add the `key` field to `TriageFinding`:

```python
class TriageFinding(BaseModel):
    signal: str  # signal id, e.g. "secrets"
    rule: str  # which rule inside it
    severity: Literal["critical", "high", "medium", "low"]
    detail: str
    path: str = ""
    line: int | None = None
    evidence: str = ""  # verbatim quote from path@commit_sha
    fix_class: FixClass
    # E-44 D3: rule-scoped discriminator, supplied by the signal when a rule
    # can fire more than once for one path. "" is correct for a rule that
    # fires at most once per path. NEVER derived from `line`: a fix landing
    # above a finding shifts it, and a delta keyed on it would report a
    # phantom resolved+new pair.
    key: str = ""
```

Then append these three functions at the end of the module, after `compute_readiness`:

```python
def finding_identity(f: TriageFinding) -> str:
    """E-44 D3. The identity a before/after delta matches on.

    Sited here rather than in delta.py because SignalResult's uniqueness
    validator needs it, and delta.py imports this module -- the other
    direction would close an import cycle.
    """
    return f"{f.signal}:{f.rule}:{f.path}:{f.key}"


def evidence_key(text: str) -> str:
    """A short stable discriminator for matched text.

    Used by rules whose only natural discriminator IS the matched line
    (misconfig's regex rules, secrets' provider rules). Hashed rather than
    stored raw so an identity is bounded in length and readable in a report;
    the raw line is already carried in `evidence`, so this hides nothing that
    is not disclosed elsewhere.
    """
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:12]


def dedupe_by_identity(findings: list[TriageFinding]) -> list[TriageFinding]:
    """Keep the first finding for each identity, in order.

    Two findings sharing an identity are the same fact reported twice -- the
    same credential on two lines of one file, the same `DEBUG = True` in two
    places. Reporting both double-counts the severity tally, and the E-44
    delta cannot key on them. Collapsing to the first occurrence is the
    behaviour SignalResult's validator (Task 2) then enforces.
    """
    seen: set[str] = set()
    out: list[TriageFinding] = []
    for f in findings:
        identity = finding_identity(f)
        if identity in seen:
            continue
        seen.add(identity)
        out.append(f)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_triage_finding_identity.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Verify no existing test regressed**

Run: `python -m pytest tests/ -k triage -q`
Expected: PASS — the `key` field defaults to `""`, so every existing signal still constructs.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/triage/models.py tests/test_triage_finding_identity.py
git commit -m "feat(triage): finding identity primitives (E-44 D3)

TriageFinding gains a signal-supplied \`key\`; identity is
(signal, rule, path, key) and never \`line\`, which drifts as soon as a
fix lands above a finding. evidence_key hashes matched text for rules
whose only discriminator is the line itself; dedupe_by_identity collapses
the same fact reported twice.

Sited in triage/models.py, not delta.py: SignalResult's validator (next
commit) needs finding_identity, and delta.py imports this module.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Signal keys, dedupe, and the uniqueness validator

**Files:**
- Modify: `src/sdlc/triage/models.py` (add the validator)
- Modify: `src/sdlc/triage/signals/secrets.py`, `misconfig.py`, `dependencies.py`, `outliers.py`
- Test: `tests/test_triage_finding_identity.py` (append)

**Interfaces:**
- Consumes: `finding_identity`, `evidence_key`, `dedupe_by_identity` from Task 1.
- Produces: the guarantee every later task relies on — **within one `SignalResult`, `finding_identity` is unique**. `baseline`, `scaffold` and `build_probe` need no change; their rules fire at most once per path.

Version bumps (the `SIGNALS` registry contract E-46 will read): `secrets` 2→3, `misconfig` 1→2, `dependencies` 1→2, `outliers` 1→2. Read each file's current `VERSION` and add one — do not assume the starting value.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_triage_finding_identity.py`:

```python
import pytest
from sdlc.measurement import Measurement
from sdlc.triage.models import SignalResult
from sdlc.triage.signals import dependencies, misconfig, outliers, secrets


def test_signal_result_rejects_duplicate_identities():
    """D3: the silent-collapse hazard is caught in the signal that caused it,
    not inherited by the delta."""
    dup = [_f(path="requirements.txt", key=""), _f(path="requirements.txt", key="")]
    with pytest.raises(ValueError, match="duplicate finding identity"):
        SignalResult(signal="deps", version=1, collected=Measurement.measured(2.0), findings=dup)


def test_signal_result_accepts_distinct_identities():
    ok = [_f(path="requirements.txt", key="flask"), _f(path="requirements.txt", key="requests")]
    r = SignalResult(signal="deps", version=1, collected=Measurement.measured(2.0), findings=ok)
    assert len(r.findings) == 2


def test_secrets_separates_two_credentials_in_one_file():
    text = "AWS_A = 'AKIAIOSFODNN7EXAMPLE'\nAWS_B = 'AKIAJJJJJJJJJJJJJJJJ'\n"
    out = secrets.scan_text("app.py", text)
    aws = [f for f in out if f.rule == "aws_access_key_id"]
    assert len(aws) == 2
    assert len({finding_identity(f) for f in aws}) == 2


def test_secrets_collapses_the_same_credential_twice_in_one_file():
    line = "AWS_A = 'AKIAIOSFODNN7EXAMPLE'\n"
    out = secrets.scan_text("app.py", line + line)
    aws = [f for f in out if f.rule == "aws_access_key_id"]
    assert len(aws) == 1
    assert aws[0].line == 1  # the first occurrence is kept


def test_misconfig_separates_two_distinct_rule_hits_in_one_file():
    blobs = {"settings.py": "DEBUG = True\napp.run(debug=True)\n"}
    out = misconfig.evaluate(blobs)
    debug = [f for f in out.findings if f.rule == "debug_enabled"]
    assert len(debug) == 2
    assert len({finding_identity(f) for f in debug}) == 2


def test_dependencies_keys_by_package_name():
    from sdlc.triage.signals.dependencies import Declared
    from sdlc.triage.advisories import AdvisoryResult

    declared = [
        Declared(name="flask", constraint=">=2", manifest="req.txt", line=1, raw="flask>=2"),
        Declared(name="requests", constraint=">=1", manifest="req.txt", line=2, raw="requests>=1"),
    ]
    out = dependencies.evaluate(
        declared,
        lockfile_present=False,
        imported={"flask", "requests"},
        advisories=AdvisoryResult(advisories=[], collected=Measurement.measured(0.0)),
    )
    unpinned = [f for f in out.findings if f.rule == "unpinned_dependency"]
    assert {f.key for f in unpinned} == {"flask", "requests"}


@pytest.mark.parametrize(
    "mod,expected", [(secrets, 3), (misconfig, 2), (dependencies, 2), (outliers, 2)]
)
def test_version_bumped(mod, expected):
    """The SIGNALS registry contract: changing what a signal emits bumps its
    version, so E-46's memo key invalidates exactly that signal."""
    assert mod.VERSION == expected
```

> If a module's current `VERSION` is not one less than `expected`, update
> `expected` in this parametrize to `current + 1` and use that value in Step 3.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_triage_finding_identity.py -v`
Expected: FAIL — the validator does not exist, so `test_signal_result_rejects_duplicate_identities` fails; the version assertions fail.

- [ ] **Step 3: Write minimal implementation**

**3a.** In `src/sdlc/triage/models.py`, add a second validator to `SignalResult`, below the existing `_not_collected_has_no_findings`:

```python
@model_validator(mode="after")
def _identities_unique(self) -> "SignalResult":
    """E-44 D3. Two findings with one identity are the same fact reported
    twice: the delta cannot key on them, and the severity tally
    double-counts. Signals collapse them with dedupe_by_identity; this
    catches the case where a new rule forgot to supply `key` at all --
    in the signal that caused it, not in the delta that inherits it."""
    seen: set[str] = set()
    for f in self.findings:
        identity = finding_identity(f)
        if identity in seen:
            raise ValueError(
                f"{self.signal}: duplicate finding identity {identity!r} "
                f"-- the rule fires more than once per path and needs a "
                f"`key` (E-44 D3)"
            )
        seen.add(identity)
    return self
```

`finding_identity` is defined below `SignalResult` in the module; that is fine — the name resolves at call time, not at class-definition time.

**3b.** `src/sdlc/triage/signals/secrets.py` — bump `VERSION` to 3. Add `key` to the local `_finding` helper and set it at the three multi-firing call sites in `scan_text`, then dedupe before returning:

```python
from ..models import (
    FixClass,
    TriageFinding,
    dedupe_by_identity,
    evidence_key,
)


def _finding(
    rule: str,
    severity: str,
    detail: str,
    fix_class: FixClass,
    path: str = "",
    line: int | None = None,
    evidence: str = "",
    key: str = "",
) -> TriageFinding:
    return TriageFinding(
        signal=SIGNAL_ID,
        rule=rule,
        severity=severity,
        detail=detail,
        fix_class=fix_class,
        path=path,
        line=line,
        evidence=evidence,
        key=key,
    )
```

In `scan_text`, the provider-rule append gains `key=evidence_key(quote)`:

```python
for rule, pattern, detail in _PROVIDER_RULES:
    if pattern.search(line):
        findings.append(
            _finding(
                rule,
                "critical",
                f"{detail} Rotate the credential; deleting the file does not revoke it.",
                FixClass.JUDGEMENT,
                path,
                lineno,
                quote,
                key=evidence_key(quote),
            )
        )
```

the client-bundle append gains `key=var`, and the generic-assignment append gains `key=ident`. Then change the final line of `scan_text` from `return findings` to:

```python
    # E-44 D3: the same credential on two lines of one file is one fact.
    return dedupe_by_identity(findings)
```

Leave `secret_committed` and `env_file_tracked` in `env_file_findings` alone — each fires at most once per repository.

**3c.** `src/sdlc/triage/signals/misconfig.py` — bump `VERSION` to 2, add `key` to `_finding` exactly as in 3b, set it on the regex-rule append:

```python
findings.append(
    _finding(
        rule,
        severity,
        detail,
        fix_class,
        path,
        lineno,
        line.strip()[:400],
        key=evidence_key(line.strip()[:400]),
    )
)
```

and dedupe in `evaluate` before constructing the `SignalResult`:

```python
    findings = dedupe_by_identity(findings)
    return SignalResult(
        signal=SIGNAL_ID, version=VERSION,
        collected=Measurement.measured(float(len(findings))),
        ...
```

Note the ordering: `collected` counts the deduped list, so the metric and the findings agree. `unauthenticated_app` is whole-application scoped and needs no key.

**3d.** `src/sdlc/triage/signals/dependencies.py` — bump `VERSION` to 2, add `key` to `_finding`, then:
- `unpinned_dependency` → `key=d.name`
- `duplicate_dependency` → `key=name`
- `known_vulnerable` → `key=f"{adv.package}:{adv.advisory_id}"` (one package can carry several advisories)
- `unused_dependency` → `key=name`

No dedupe call is needed here — each loop already iterates a set or a sorted unique key — but add `findings = dedupe_by_identity(findings)` before the `SignalResult` anyway, so a future rule cannot reintroduce the hazard silently.

**3e.** `src/sdlc/triage/signals/outliers.py` — bump `VERSION` to 2, add `key` to `_finding`, then:
- `oversized_file` → no key (one per path)
- `oversized_function` → `key=name` (the function name; two oversized functions can share a file)
- `duplicated_block` → `key=",".join(paths)` (the clone group's path set)

and dedupe before the `SignalResult`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_triage_finding_identity.py -v`
Expected: PASS

- [ ] **Step 5: Run the full triage suite**

Run: `python -m pytest tests/ -k triage -q`
Expected: PASS. If a signal test now fails on a *count*, that is this task's deliberate dedupe collapsing a double-report — update the expected count in that test and note it in the commit body. If it fails with `duplicate finding identity`, a rule still needs a `key`; add one following the pattern above.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/triage/
git add tests/test_triage_finding_identity.py
git commit -m "feat(triage): signal-supplied finding keys + uniqueness validator (E-44 D3)

secrets/misconfig/dependencies/outliers set \`key\` wherever a rule can
fire more than once for one path, and dedupe before emitting. SignalResult
now rejects duplicate identities, so a future rule that forgets \`key\`
fails in the signal that caused it rather than silently collapsing three
unpinned dependencies into one delta entry.

Deliberate behaviour change: the same credential on two lines of one file,
or the same DEBUG = True twice, is now one finding. It was one fact
reported twice, and it double-counted the severity tally.

Versions bumped so E-46's memo key invalidates exactly these four.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: `compute_delta`

**Files:**
- Create: `src/sdlc/triage/delta.py`
- Test: `tests/test_triage_delta.py`

**Interfaces:**
- Consumes: `finding_identity`, `RepoTriage`, `SignalResult`, `TriageFinding` from `sdlc.triage.models`; `CollectionState` from `sdlc.measurement`.
- Produces: `FindingState` (enum: `RESOLVED`/`PERSISTED`/`NEW`/`UNVERIFIABLE`), `FindingDelta`, and
  `compute_delta(before: RepoTriage, after: RepoTriage | None, conflicted: Sequence[str] = ()) -> list[FindingDelta]`.
  Task 7 calls exactly this signature.

- [ ] **Step 1: Write the failing test**

Create `tests/test_triage_delta.py`:

```python
"""D4/D5: compute_delta is the only producer of a FindingState, and absence is
never read as resolution. Each honesty rule gets a test."""

import pytest

from sdlc.measurement import Measurement
from sdlc.triage.delta import FindingDelta, FindingState, compute_delta
from sdlc.triage.models import (
    FixClass,
    Readiness,
    RepoTriage,
    SignalResult,
    TriageFinding,
    Verdict,
)


def _finding(rule="gitignore_missing", key="", signal="baseline"):
    return TriageFinding(
        signal=signal,
        rule=rule,
        severity="medium",
        detail="d",
        path=".gitignore",
        key=key,
        fix_class=FixClass.MECHANICAL,
    )


def _sig(signal="baseline", version=2, findings=(), collected=None):
    return SignalResult(
        signal=signal,
        version=version,
        collected=collected or Measurement.measured(float(len(findings))),
        findings=list(findings),
    )


def _triage(*signals):
    m = Measurement.measured(1.0)
    return RepoTriage(
        repo_dir="/r",
        commit_sha="a" * 40,
        readiness=Readiness(
            buildable=m, runnable=m, tests_present=m, structure_discernible=m, verdict=Verdict.READY
        ),
        signals=list(signals),
    )


def test_present_before_absent_after_is_resolved():
    out = compute_delta(_triage(_sig(findings=[_finding()])), _triage(_sig(findings=[])))
    assert [d.state for d in out] == [FindingState.RESOLVED]


def test_present_in_both_is_persisted():
    out = compute_delta(_triage(_sig(findings=[_finding()])), _triage(_sig(findings=[_finding()])))
    assert [d.state for d in out] == [FindingState.PERSISTED]


def test_present_only_after_is_new():
    out = compute_delta(_triage(_sig(findings=[])), _triage(_sig(findings=[_finding()])))
    assert [d.state for d in out] == [FindingState.NEW]


def test_signal_not_collected_after_is_unverifiable_not_resolved():
    """D5 rule 1. The load-bearing one: a signal that timed out on the after
    side would otherwise read as having fixed everything it found."""
    after = _triage(_sig(findings=[], collected=Measurement.not_collected("timed out")))
    out = compute_delta(_triage(_sig(findings=[_finding()])), after)
    assert [d.state for d in out] == [FindingState.UNVERIFIABLE]
    assert "timed out" in out[0].reason


def test_signal_not_collected_before_is_also_unverifiable():
    before = _triage(_sig(findings=[], collected=Measurement.not_collected("git failed")))
    out = compute_delta(before, _triage(_sig(findings=[_finding()])))
    assert [d.state for d in out] == [FindingState.UNVERIFIABLE]


def test_signal_absent_from_the_after_side_is_unverifiable():
    out = compute_delta(_triage(_sig(findings=[_finding()])), _triage())
    assert [d.state for d in out] == [FindingState.UNVERIFIABLE]
    assert "did not report" in out[0].reason


def test_version_mismatch_is_unverifiable():
    """D5 rule 2: a rule that changed between the two triages did not measure
    the same thing twice."""
    out = compute_delta(
        _triage(_sig(version=2, findings=[_finding()])), _triage(_sig(version=3, findings=[]))
    )
    assert [d.state for d in out] == [FindingState.UNVERIFIABLE]
    assert "version" in out[0].reason


def test_conflicted_identity_is_unverifiable_not_persisted():
    """D5 rule 3: the fix is real but absent from the tree we measured."""
    f = _finding()
    identity = "baseline:gitignore_missing:.gitignore:"
    out = compute_delta(
        _triage(_sig(findings=[f])), _triage(_sig(findings=[f])), conflicted=[identity]
    )
    assert [d.state for d in out] == [FindingState.UNVERIFIABLE]
    assert "conflict" in out[0].reason


def test_after_is_none_marks_every_identity_unverifiable():
    """D5 rule 4: never an empty delta reading as 'nothing resolved'."""
    out = compute_delta(_triage(_sig(findings=[_finding(key="a"), _finding(key="b")])), None)
    assert len(out) == 2
    assert all(d.state is FindingState.UNVERIFIABLE for d in out)
    assert all(d.reason for d in out)


def test_output_is_sorted_by_identity():
    before = _triage(_sig(findings=[_finding(key="z"), _finding(key="a")]))
    out = compute_delta(before, _triage(_sig(findings=[])))
    assert [d.identity for d in out] == sorted(d.identity for d in out)


def test_delta_carries_the_findings_own_signal_rule_and_severity():
    out = compute_delta(_triage(_sig(findings=[_finding()])), _triage(_sig(findings=[])))
    assert (out[0].signal, out[0].rule, out[0].severity) == (
        "baseline",
        "gitignore_missing",
        "medium",
    )


def test_unverifiable_requires_a_reason():
    with pytest.raises(ValueError, match="reason"):
        FindingDelta(
            identity="i", signal="s", rule="r", severity="low", state=FindingState.UNVERIFIABLE
        )


def test_a_measured_state_does_not_require_a_reason():
    d = FindingDelta(
        identity="i", signal="s", rule="r", severity="low", state=FindingState.RESOLVED
    )
    assert d.reason == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_triage_delta.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.triage.delta'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/triage/delta.py`:

```python
"""FR-904 (E-44): the before/after triage delta.

Pure by design -- Pydantic, stdlib, `.models` and `..measurement` only, exactly
as models.py and grounding.py are. A dependency on temporalio or the root
models.py would appear as a reviewable import.

`compute_delta` is the ONLY producer of a FindingState (D4), mirroring
compute_readiness's relationship to Verdict: no caller sets a state, so a
TidyUpReport cannot disagree with its own inputs.

This is deliberately NOT a set difference. A naive before-minus-after diff
reads ABSENCE as RESOLUTION -- so a signal that timed out on the after side
would report every finding it had found as fixed. That is the same conflation
E-40 removed from report_from_sarif, which returned critical=0 for a malformed
document. Five conditions (D5) produce UNVERIFIABLE instead.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
from typing import Literal

from pydantic import BaseModel, model_validator

from ..measurement import CollectionState
from .models import RepoTriage, SignalResult, TriageFinding, finding_identity


class FindingState(str, Enum):
    RESOLVED = "resolved"  # present before, absent after
    PERSISTED = "persisted"  # present in both
    NEW = "new"  # absent before, present after
    UNVERIFIABLE = "unverifiable"  # not measurable on one side


class FindingDelta(BaseModel):
    identity: str
    signal: str
    rule: str
    severity: Literal["critical", "high", "medium", "low"]
    state: FindingState
    reason: str = ""

    @model_validator(mode="after")
    def _unverifiable_states_a_reason(self) -> "FindingDelta":
        if self.state is FindingState.UNVERIFIABLE and not self.reason:
            raise ValueError(
                f"{self.identity}: UNVERIFIABLE without a reason -- the whole "
                f"point of the state is that it says WHY it could not be "
                f"measured"
            )
        return self


def _unusable(
    signal_id: str, before: dict[str, SignalResult], after: dict[str, SignalResult]
) -> str:
    """Why this signal's findings cannot be compared, or "" when they can."""
    b, a = before.get(signal_id), after.get(signal_id)
    for side, result in (("before", b), ("after", a)):
        if result is None:
            return (
                f"signal {signal_id!r} did not report on the {side} "
                f"side, so its findings were never compared"
            )
        if result.collected.state is not CollectionState.MEASURED:
            return (
                f"signal {signal_id!r} did not collect on the {side} "
                f"side: {result.collected.reason}"
            )
    if b.version != a.version:
        return (
            f"signal {signal_id!r} changed version between the two "
            f"triages (v{b.version} -> v{a.version}), so the two runs "
            f"did not measure the same thing"
        )
    return ""


def _delta(identity: str, f: TriageFinding, state: FindingState, reason: str = "") -> FindingDelta:
    return FindingDelta(
        identity=identity,
        signal=f.signal,
        rule=f.rule,
        severity=f.severity,
        state=state,
        reason=reason,
    )


def compute_delta(
    before: RepoTriage, after: RepoTriage | None, conflicted: Sequence[str] = ()
) -> list[FindingDelta]:
    """Classify every finding across the two triages.

    `conflicted` carries the identities whose fix branch failed to merge into
    the verification tree (D6). Their findings are present in `after` because
    the fix is not in the tree being measured -- reporting them PERSISTED
    would be true of that tree and misleading about the fix, so they are
    UNVERIFIABLE (D5 rule 3).
    """
    blocked = set(conflicted)
    before_f = {finding_identity(f): f for s in before.signals for f in s.findings}

    if after is None:
        # D5 rule 4. Never an empty delta: "nothing resolved" and "nothing
        # was measured" must not render identically.
        return [
            _delta(
                i,
                before_f[i],
                FindingState.UNVERIFIABLE,
                "no verification tree was produced, so the after state was never measured",
            )
            for i in sorted(before_f)
        ]

    after_f = {finding_identity(f): f for s in after.signals for f in s.findings}
    before_s = {s.signal: s for s in before.signals}
    after_s = {s.signal: s for s in after.signals}

    out: list[FindingDelta] = []
    for identity in sorted(set(before_f) | set(after_f)):
        f = before_f.get(identity) or after_f[identity]

        reason = _unusable(f.signal, before_s, after_s)
        if reason:
            out.append(_delta(identity, f, FindingState.UNVERIFIABLE, reason))
            continue
        if identity in blocked:
            out.append(
                _delta(
                    identity,
                    f,
                    FindingState.UNVERIFIABLE,
                    "the fix branch for this finding hit a merge conflict and is "
                    "not in the verification tree",
                )
            )
            continue
        if identity in before_f and identity in after_f:
            out.append(_delta(identity, f, FindingState.PERSISTED))
        elif identity in before_f:
            out.append(_delta(identity, f, FindingState.RESOLVED))
        else:
            out.append(_delta(identity, f, FindingState.NEW))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_triage_delta.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Verify purity**

Run: `python -m pytest tests/ -k triage -q`
Then confirm by eye that `src/sdlc/triage/delta.py` imports nothing from `sdlc.models`, `sdlc.activities`, or `temporalio`.

Run: `grep -nE "^(from|import).*(temporalio|\.\.models|\.\.activities)" src/sdlc/triage/delta.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/triage/delta.py tests/test_triage_delta.py
git commit -m "feat(triage): compute_delta, the only producer of a FindingState (E-44 D4/D5)

Deliberately not a set difference. A before-minus-after diff reads absence
as resolution, so a signal that timed out on the after side would report
everything it had found as fixed -- the conflation E-40 removed from
report_from_sarif's critical=0.

Five conditions produce UNVERIFIABLE instead: signal absent on a side,
signal not collected on a side, signal version changed between the runs,
the fix branch conflicted, and no verification tree at all. The last one
is why after=None returns every identity rather than an empty list:
'nothing resolved' and 'nothing measured' must not render identically.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: `SeededWork` and the `FeatureWorkflow` entry point

**Files:**
- Modify: `src/sdlc/models.py`
- Modify: `src/sdlc/workflows/feature.py` (`run` ~line 1589, `_pipeline` ~line 1667, stage 4 entry ~line 2069)
- Test: `tests/test_seeded_work.py`

**Interfaces:**
- Consumes: `ArchitectureSpec`, `ImplementationPlan` (existing, `sdlc.models`).
- Produces: `SeededWork(arch: ArchitectureSpec, plan: ImplementationPlan)` in `sdlc.models`; `FeatureWorkflow.run(idea, cfg=None, seeded=None)`. Task 7 starts children with exactly this three-argument form.

Read `feature.py:1589-1600` (`run`), `1667-1690` (`_pipeline` head), and `2018-2075` (plan stage → stage 4) before editing.

- [ ] **Step 1: Write the failing test**

Create `tests/test_seeded_work.py`:

```python
"""D1: a seeded run skips stages 0-3 and keeps everything from _dev_task down.

The unit tests here pin the contract and the skip predicate; the end-to-end
'no proposer was called' assertion is the temporal test at the bottom.
"""

import inspect

import pytest

from sdlc.models import (
    ArchitectureSpec,
    ArchitectureDecision,
    DevTask,
    ImplementationPlan,
    SeededWork,
    ValidationContract,
)
from sdlc.workflows.feature import FeatureWorkflow


def _seeded():
    return SeededWork(
        arch=ArchitectureSpec(
            overview="Tidy-up: add .env to .gitignore",
            decisions=[
                ArchitectureDecision(
                    id="D1",
                    decision="Edit .gitignore only",
                    rationale="triage finding baseline/gitignore_missing_env",
                )
            ],
        ),
        plan=ImplementationPlan(
            tasks=[
                DevTask(
                    id="T01",
                    title="gitignore_missing_env in .gitignore",
                    description="Add .env to .gitignore.",
                    acceptance_criteria=["triage no longer reports the rule"],
                    files_hint=[".gitignore"],
                    contract=ValidationContract(
                        task_id="T01", assertions=[".env is ignored"], frozen=True
                    ),
                )
            ]
        ),
    )


def test_seeded_work_carries_an_arch_and_a_plan():
    s = _seeded()
    assert s.arch.overview.startswith("Tidy-up")
    assert [t.id for t in s.plan.tasks] == ["T01"]


def test_seeded_work_round_trips_through_json():
    """It crosses a Temporal child-workflow boundary, so it must serialize."""
    s = _seeded()
    assert SeededWork.model_validate_json(s.model_dump_json()) == s


def test_run_accepts_seeded_as_a_third_argument():
    sig = inspect.signature(FeatureWorkflow.run)
    params = list(sig.parameters)
    assert params[1:] == ["idea", "cfg", "seeded"], (
        "Task 7 starts children with args=[idea, cfg, seeded]; the order and names are the contract"
    )
    assert sig.parameters["seeded"].default is None


def test_seeded_plan_must_carry_at_least_one_task():
    with pytest.raises(ValueError):
        SeededWork(arch=_seeded().arch, plan=ImplementationPlan(tasks=[]))
```

Add the temporal half in the same file:

```python
@pytest.mark.temporal
async def test_seeded_run_never_calls_clarify_architect_or_planner():
    """The whole point of D1: six model calls for a one-line fix is what this
    avoids. Follows tests/test_e2e_greenfield.py's fake-agent wiring."""
    from tests.fakes.fake_agents import calls_recorded, register_fakes  # noqa

    # Drive a seeded FeatureWorkflow through the fake harness/agent stubs the
    # existing e2e test uses, then assert on the recorded proposer calls.
    recorded = await _run_seeded_pipeline(_seeded())
    assert "clarifier" not in recorded
    assert "architect" not in recorded
    assert "planner" not in recorded
    assert "reviewer" in recorded, (
        "review must still run -- ADR-6 is the reason a seeded run is still governed"
    )
```

> `_run_seeded_pipeline` and the exact fake-agent import are to be written by
> following `tests/test_e2e_greenfield.py`'s existing worker setup verbatim —
> open that file, copy its `WorkflowEnvironment` / `Worker` block, and pass
> `args=[idea, cfg, seeded]` to `execute_workflow` instead of `args=[idea, cfg]`.
> Do not invent a new fixture; the point of this test is that the *existing*
> harness runs a seeded input unchanged.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_seeded_work.py -v`
Expected: FAIL — `ImportError: cannot import name 'SeededWork' from 'sdlc.models'`

- [ ] **Step 3: Write minimal implementation**

**3a.** In `src/sdlc/models.py`, add below `ImplementationPlan`:

```python
class SeededWork(BaseModel):
    """E-44 D1: an ImplementationPlan authored deterministically rather than by
    the planner.

    A FeatureWorkflow handed one of these skips stages 0-3 (research, clarify,
    architecture, planning) and enters at the code stage. Everything from
    _dev_task down is unchanged and still binding -- clean-context review
    (ADR-6/FR-204), the bounded fix loop (FR-105), the deterministic quality
    gate (FR-106), the merge gate. Those are the stages that make a run
    GOVERNED (NG5); stages 0-3 decide WHAT to build, and for a mechanical
    triage finding the finding itself already answers that.

    `arch` is seeded rather than made optional because after planning it is
    read at exactly one place -- the PR body -- so seeding it keeps stage 4
    onward free of `| None` handling.
    """

    arch: ArchitectureSpec
    plan: ImplementationPlan

    @model_validator(mode="after")
    def _plan_is_not_empty(self) -> "SeededWork":
        if not self.plan.tasks:
            raise ValueError(
                "SeededWork with no tasks would open an empty PR -- the "
                "vacuous-task bypass SC-5 already closed once"
            )
        return self
```

**3b.** In `src/sdlc/workflows/feature.py`, add `SeededWork` to the `..models` import block inside `workflow.unsafe.imports_passed_through()`.

**3c.** Change the `run` signature (~line 1589):

```python
async def run(
    self, idea: IdeaBrief, cfg: PipelineConfig | None = None, seeded: SeededWork | None = None
) -> str:
    cfg = cfg or PipelineConfig()
    self._cfg = cfg
    self._budget_threshold = cfg.run_budget_usd  # E-33
    try:
        result = await self._pipeline(idea, cfg, seeded)
    except _BudgetRejected:
        result = "rejected:budget"
    await self._retro(cfg, idea, result)
    return result
```

**3d.** Change `_pipeline`'s signature to
`async def _pipeline(self, idea, cfg, seeded: SeededWork | None = None) -> str:`.

**3e.** Wrap stages 0–3. The integration-branch setup at the head of `_pipeline`
(`setup_integration_branch`, ~line 1683) must **still run** — a seeded run needs
its worktree. Immediately after `self._integration_wt = integration.worktree_path`,
insert:

```python
# E-44 D1: a seeded run enters at stage 4. Research, clarify,
# architecture and planning decide WHAT to build; a mechanical triage
# finding already answers that, and clarify's open-question wait would
# park a tidy-up run on a question the finding contains.
if seeded is not None:
    arch, plan = seeded.arch, seeded.plan
    self._status = "coding"
    return await self._build_and_merge(idea, cfg, arch, plan, repo_path)
```

Then extract the existing body from the `# 4. DEV / TEST / DEVOPS tasks`
comment (~line 2069) to the end of `_pipeline` into a new method:

```python
async def _build_and_merge(
    self,
    idea: IdeaBrief,
    cfg: PipelineConfig,
    arch: ArchitectureSpec,
    plan: ImplementationPlan,
    repo_path: str,
) -> str:
    """Stages 4-6: tasks, merge gate, PR, deploy. Shared by the ordinary
    pipeline and by E-44's seeded entry point -- one implementation of
    'how a governed change reaches a PR' (D1)."""
```

and have the ordinary path end with `return await self._build_and_merge(idea, cfg, arch, plan, repo_path)` where its body used to continue. This is a **pure move**: do not change a line of the moved code, only its indentation and the names it now takes as parameters (`arch`, `plan`, `repo_path` were locals; everything else is `self` or `cfg`).

The board publish for the seeded plan (`self._plan_version`) lives in stage 3, which a seeded run skips — that is correct. `_board_sync_tasks` is likewise skipped; a tidy-up run's tasks are recorded in its own `TidyUpReport`, and adding a board projection for them is out of scope.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_seeded_work.py -v`
Expected: PASS on the four unit tests.

Run: `python -m pytest tests/test_seeded_work.py -m temporal -v`
Expected: PASS.

- [ ] **Step 5: Verify the ordinary pipeline is unchanged**

Run: `python -m pytest tests/ -q`
Then: `python -m pytest -m temporal -q`
Expected: PASS. The extraction is a pure move; any failure here means a name was dropped or the indentation changed a branch.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/models.py src/sdlc/workflows/feature.py tests/test_seeded_work.py
git commit -m "feat(pipeline): SeededWork entry point at stage 4 (E-44 D1)

A FeatureWorkflow handed a SeededWork skips research/clarify/architecture/
planning and enters at the code stage. Everything from _dev_task down is
untouched and still binding: clean-context review, the bounded fix loop,
the deterministic quality gate, the merge gate. Those are the stages that
make a run governed under NG5; stages 0-3 decide what to build, and a
mechanical triage finding already answers that.

Stages 4-6 extracted verbatim into _build_and_merge so the ordinary path
and the seeded path share one implementation of 'how a governed change
reaches a PR'. A second copy is the shape ADR-6 and STAGE_MODELS each cost
us once.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: `build_verification_branch`

**Files:**
- Modify: `src/sdlc/activities.py` (beside `merge_into_integration`, ~line 352)
- Test: `tests/test_verification_branch.py`

**Interfaces:**
- Consumes: the module-private `_git(args, cwd)` helper already in `activities.py`.
- Produces: `VerifyBranchInput(repo_path, base_sha, tidyup_id, branches: list[str])` and `VerifyResult(ref, head_sha, merged: list[str], conflicted: list[str])`, plus the `@activity.defn build_verification_branch`. Task 7 calls it; Task 8 registers it.

Both are `@dataclass`, matching `MergeInput`/`MergeResult` in the same file — not Pydantic. Follow the file's existing convention.

- [ ] **Step 1: Write the failing test**

Create `tests/test_verification_branch.py`:

```python
"""D6: the fixes live on unmerged branches, so the tree to re-triage has to be
constructed. Real git in a tmp repo -- the activity is git behaviour, and a
mocked subprocess would test the mock."""

import subprocess

import pytest

from sdlc.activities import (
    VerifyBranchInput,
    build_verification_branch,
)


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(["init", "-b", "main"], r)
    _git(["config", "user.email", "t@t"], r)
    _git(["config", "user.name", "t"], r)
    (r / "a.txt").write_text("base\n")
    _git(["add", "-A"], r)
    _git(["commit", "-m", "base"], r)
    base = _git(["rev-parse", "HEAD"], r).stdout.strip()
    return r, base


def _branch_with(repo_dir, name, filename, content, base):
    _git(["checkout", "-q", "-b", name, base], repo_dir)
    (repo_dir / filename).write_text(content)
    _git(["add", "-A"], repo_dir)
    _git(["commit", "-q", "-m", name], repo_dir)
    _git(["checkout", "-q", "main"], repo_dir)


async def test_merges_every_branch_and_reports_the_head(repo):
    r, base = repo
    _branch_with(r, "fix1", "b.txt", "one\n", base)
    _branch_with(r, "fix2", "c.txt", "two\n", base)
    out = await build_verification_branch(
        VerifyBranchInput(
            repo_path=str(r), base_sha=base, tidyup_id="t1", branches=["fix1", "fix2"]
        )
    )
    assert out.merged == ["fix1", "fix2"]
    assert out.conflicted == []
    assert out.head_sha != base
    assert "t1" in out.ref


async def test_a_conflicting_branch_is_recorded_and_the_rest_still_merge(repo):
    r, base = repo
    _branch_with(r, "fix1", "shared.txt", "one\n", base)
    _branch_with(r, "fix2", "shared.txt", "two\n", base)
    _branch_with(r, "fix3", "d.txt", "three\n", base)
    out = await build_verification_branch(
        VerifyBranchInput(
            repo_path=str(r), base_sha=base, tidyup_id="t2", branches=["fix1", "fix2", "fix3"]
        )
    )
    assert out.merged == ["fix1", "fix3"]
    assert out.conflicted == ["fix2"]


async def test_no_branches_yields_the_base_and_merges_nothing(repo):
    r, base = repo
    out = await build_verification_branch(
        VerifyBranchInput(repo_path=str(r), base_sha=base, tidyup_id="t3", branches=[])
    )
    assert out.merged == [] and out.conflicted == []
    assert out.head_sha == base


async def test_the_verification_ref_is_local_and_never_pushed(repo):
    """Operator-run; delivery is PR-only until FR-1003/E-59."""
    r, base = repo
    _branch_with(r, "fix1", "b.txt", "one\n", base)
    out = await build_verification_branch(
        VerifyBranchInput(repo_path=str(r), base_sha=base, tidyup_id="t4", branches=["fix1"])
    )
    remotes = _git(["remote"], r).stdout.strip()
    assert remotes == "", "the fixture has no remote; nothing may add one"
    assert out.ref.startswith("sdlc/tidyup-verify/")


async def test_is_idempotent_across_a_retry(repo):
    """Temporal retries activities. A second call with the same tidyup_id must
    not fail on 'branch already exists'."""
    r, base = repo
    _branch_with(r, "fix1", "b.txt", "one\n", base)
    inp = VerifyBranchInput(repo_path=str(r), base_sha=base, tidyup_id="t5", branches=["fix1"])
    first = await build_verification_branch(inp)
    second = await build_verification_branch(inp)
    assert first.head_sha == second.head_sha
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_verification_branch.py -v`
Expected: FAIL — `ImportError: cannot import name 'VerifyBranchInput'`

- [ ] **Step 3: Write minimal implementation**

In `src/sdlc/activities.py`, immediately after `merge_into_integration`:

```python
@dataclass
class VerifyBranchInput:
    repo_path: str
    base_sha: str  # the commit the baseline triage pinned
    tidyup_id: str  # the TidyUpWorkflow's id -- makes the ref unique
    branches: list[str]  # fix-run integration branches, in accepted order


@dataclass
class VerifyResult:
    ref: str
    head_sha: str
    merged: list[str]
    conflicted: list[str]


@activity.defn
async def build_verification_branch(inp: VerifyBranchInput) -> VerifyResult:
    """E-44 D6: the tree the after-triage measures.

    open_pull_request OPENS PRs; it does not merge them, so re-triaging the
    base branch would measure a tree containing none of the fixes. This builds
    the 'if you merged all of these' tree instead: a local branch off the
    pinned commit with every successful fix branch merged into it.

    Local only -- never pushed. Delivery stays PR-only until FR-1003/E-59.

    A conflict between two fix branches is a RESULT, not a failure: the merge
    is aborted, the branch is recorded in `conflicted`, and the remaining
    branches still merge. compute_delta then marks that identity UNVERIFIABLE
    rather than PERSISTED (D5 rule 3).

    Idempotent: Temporal retries activities, so the branch is force-created
    at `base_sha` on every call and the merges replayed from there.
    """
    ref = f"sdlc/tidyup-verify/{inp.tidyup_id}"
    # -B force-creates: a retry resets to base_sha rather than failing on an
    # existing branch or compounding merges onto a half-built tree.
    _git(["checkout", "-q", "-B", ref, inp.base_sha], inp.repo_path)

    merged: list[str] = []
    conflicted: list[str] = []
    for branch in inp.branches:
        result = _git(["merge", "--no-ff", "-m", f"tidy-up: {branch}", branch], inp.repo_path)
        if result.returncode == 0:
            merged.append(branch)
            continue
        # Distinguish a real conflict from an infra failure via the index's
        # unmerged entries (locale-independent), and read it BEFORE
        # `merge --abort`, which clears the unmerged state. Same reasoning as
        # merge_into_integration.
        unmerged = _git(["ls-files", "--unmerged"], inp.repo_path).stdout
        _git(["merge", "--abort"], inp.repo_path)
        if not unmerged.strip():
            raise RuntimeError(
                f"git merge of {branch} failed (not a conflict): {result.stderr.strip()}"
            )
        conflicted.append(branch)

    head = _git(["rev-parse", "HEAD"], inp.repo_path).stdout.strip()
    return VerifyResult(ref=ref, head_sha=head, merged=merged, conflicted=conflicted)
```

Check `_git`'s signature in the file before writing — if it is `_git(args, cwd)` positionally, the calls above are correct as written.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_verification_branch.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/activities.py tests/test_verification_branch.py
git commit -m "feat(activities): build_verification_branch (E-44 D6)

open_pull_request opens PRs and does not merge them, so re-triaging the
base branch would measure a tree containing none of the fixes. This builds
the 'if you merged all of these' tree: a local branch off the pinned
commit with every fix branch merged in.

A conflict between two fix branches is a result, not a failure -- abort,
record, keep going. compute_delta marks that identity UNVERIFIABLE rather
than PERSISTED, because the finding persisting in this tree says nothing
about whether the fix works.

Force-creates the branch at base_sha so a Temporal activity retry replays
from the pinned commit instead of compounding onto a half-built tree.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Backlog materialization and task authoring

**Files:**
- Create: `src/sdlc/tidyup/__init__.py`, `src/sdlc/tidyup/backlog.py`
- Test: `tests/test_tidyup_backlog.py`

**Interfaces:**
- Consumes: `FixClass`, `RepoTriage`, `TriageFinding`, `finding_identity` (Task 1); `SeededWork` (Task 4).
- Produces:
  - `mechanical_backlog(triage: RepoTriage) -> list[tuple[str, TriageFinding]]` — sorted by identity
  - `seeded_work_for(identity: str, f: TriageFinding, signal_version: int) -> SeededWork`
  - `admitted(triage: RepoTriage) -> bool`

  Task 7 imports all three.

Pure module: no `temporalio`. It may import `sdlc.models` (unlike `triage/`) because it *builds* pipeline contracts — that is its whole job.

- [ ] **Step 1: Write the failing test**

Create `tests/test_tidyup_backlog.py`:

```python
"""D7/D10 and the authored DevTask. Pure -- no Temporal."""

import pytest

from sdlc.measurement import Measurement
from sdlc.tidyup.backlog import admitted, mechanical_backlog, seeded_work_for
from sdlc.triage.models import (
    FixClass,
    Readiness,
    ReadinessOverride,
    RepoTriage,
    SignalResult,
    TriageFinding,
    Verdict,
)
from datetime import datetime, timezone


def _f(rule, fix_class=FixClass.MECHANICAL, key="", path="p", signal="s"):
    return TriageFinding(
        signal=signal,
        rule=rule,
        severity="high",
        detail=f"{rule} detail",
        path=path,
        key=key,
        evidence="the offending line",
        fix_class=fix_class,
    )


def _triage(findings, verdict=Verdict.READY, override=None):
    m = Measurement.measured(1.0)
    return RepoTriage(
        repo_dir="/r",
        commit_sha="a" * 40,
        override=override,
        readiness=Readiness(
            buildable=m, runnable=m, tests_present=m, structure_discernible=m, verdict=verdict
        ),
        signals=[
            SignalResult(
                signal="s",
                version=4,
                collected=Measurement.measured(float(len(findings))),
                findings=findings,
            )
        ],
    )


def test_backlog_holds_only_mechanical_findings():
    t = _triage([_f("a"), _f("b", FixClass.JUDGEMENT), _f("c", FixClass.STRUCTURAL)])
    assert [f.rule for _, f in mechanical_backlog(t)] == ["a"]


def test_backlog_is_sorted_by_identity():
    """D10: child workflow ids derive from position, and replay must produce
    the same ids."""
    t = _triage([_f("z", key="1"), _f("a", key="2")])
    ids = [i for i, _ in mechanical_backlog(t)]
    assert ids == sorted(ids)


def test_backlog_is_empty_when_nothing_is_mechanical():
    assert mechanical_backlog(_triage([_f("a", FixClass.JUDGEMENT)])) == []


def test_admitted_on_ready():
    assert admitted(_triage([], Verdict.READY)) is True


@pytest.mark.parametrize("verdict", [Verdict.NOT_READY, Verdict.INDETERMINATE])
def test_not_admitted_without_an_override(verdict):
    assert admitted(_triage([], verdict)) is False


@pytest.mark.parametrize("verdict", [Verdict.NOT_READY, Verdict.INDETERMINATE])
def test_admitted_with_an_audited_override(verdict):
    """D7: E-42's rule verbatim -- READY or override is not None."""
    o = ReadinessOverride(
        approved_by="human",
        reason="proceeding anyway",
        decided_at=datetime.now(timezone.utc),
        gate_round=1,
    )
    assert admitted(_triage([], verdict, override=o)) is True


def test_seeded_work_has_exactly_one_task():
    s = seeded_work_for("s:a:p:", _f("a"), signal_version=4)
    assert len(s.plan.tasks) == 1


def test_authored_task_names_the_rule_the_path_and_the_evidence():
    s = seeded_work_for("s:a:p:", _f("a"), signal_version=4)
    t = s.plan.tasks[0]
    assert "a" in t.title and "p" in t.title
    assert "the offending line" in t.description
    assert t.files_hint == ["p"]
    assert t.role == "dev"


def test_authored_task_constrains_the_change():
    """One PR per finding means the run must not wander."""
    t = seeded_work_for("s:a:p:", _f("a"), signal_version=4).plan.tasks[0]
    assert "Change nothing else" in t.description


def test_acceptance_criterion_names_the_signal_rule_and_version():
    t = seeded_work_for("s:a:p:", _f("a"), signal_version=4).plan.tasks[0]
    criterion = t.acceptance_criteria[0]
    assert "s" in criterion and "a" in criterion and "4" in criterion


def test_contract_is_frozen_at_acceptance():
    """FR-803 freezes at planning, before code. Backlog acceptance is the
    analogous moment: still before code, deterministic producer."""
    t = seeded_work_for("s:a:p:", _f("a"), signal_version=4).plan.tasks[0]
    assert t.contract is not None
    assert t.contract.frozen is True
    assert t.contract.task_id == t.id


def test_arch_overview_becomes_a_usable_pr_body():
    s = seeded_work_for("s:a:p:", _f("a"), signal_version=4)
    assert "a" in s.arch.overview
    assert s.arch.decisions, "the PR body should say why the change is scoped"


def test_a_finding_with_no_path_still_authors_a_task():
    """no_env_example carries path=''."""
    s = seeded_work_for("s:x::", _f("x", path=""), signal_version=4)
    assert s.plan.tasks[0].files_hint == []
    assert s.plan.tasks[0].title
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tidyup_backlog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.tidyup'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/tidyup/__init__.py` (empty file).

Create `src/sdlc/tidyup/backlog.py`:

```python
"""FR-904 (E-44): what gets fixed, and the work handed to a fix run.

Pure -- no temporalio. Unlike `triage/`, this module MAY import the root
models.py: building pipeline contracts from triage findings is its whole job.
"""

from __future__ import annotations

from ..models import (
    ArchitectureDecision,
    ArchitectureSpec,
    DevTask,
    ImplementationPlan,
    SeededWork,
    ValidationContract,
)
from ..triage.models import (
    FixClass,
    RepoTriage,
    TriageFinding,
    Verdict,
    finding_identity,
)


def admitted(triage: RepoTriage) -> bool:
    """D7. E-42's admission rule verbatim -- the same line E-45 will use.

    FR-903's gate blocks Tier 2, not tidy-up, so this is not automatic. It is
    adopted for a mechanical reason: on a repository that does not build,
    build_integration_green is an ABSOLUTE merge-gate check, so every fix run
    would produce a correct patch and then be blocked. That is N runs of model
    spend to learn what the build probe already reported.
    """
    return triage.readiness.verdict is Verdict.READY or triage.override is not None


def mechanical_backlog(triage: RepoTriage) -> list[tuple[str, TriageFinding]]:
    """Every MECHANICAL finding, as (identity, finding), sorted by identity.

    Sorting is load-bearing, not cosmetic (D10): child workflow ids derive
    from a finding's position in this list, and Temporal replay must produce
    the same ids.
    """
    out = [
        (finding_identity(f), f)
        for s in triage.signals
        for f in s.findings
        if f.fix_class is FixClass.MECHANICAL
    ]
    out.sort(key=lambda pair: pair[0])
    return out


def seeded_work_for(identity: str, f: TriageFinding, signal_version: int) -> SeededWork:
    """The deterministically-authored work for one mechanical finding (D1).

    One task, because one accepted finding is one PR (D2). The acceptance
    criterion names the signal, rule and version, so the reviewer and QA are
    validating against the thing that produced the finding rather than
    against the harness's narrative.
    """
    where = f.path or "the repository"
    title = f"{f.rule} in {where}"

    evidence = f"\n\nThe line that triggered it:\n{f.evidence}" if f.evidence else ""
    description = (
        f"Triage finding `{identity}` (severity: {f.severity}).\n\n"
        f"{f.detail}{evidence}\n\n"
        f"Fix exactly this finding. Change nothing else -- this run opens one "
        f"pull request for one finding, and unrelated edits make it "
        f"un-reviewable."
    )

    criterion = (
        f"re-running triage signal `{f.signal}` v{signal_version} no "
        f"longer reports `{f.rule}` for `{where}`"
    )

    task = DevTask(
        id="T01",
        role="dev",
        title=title,
        description=description,
        acceptance_criteria=[criterion],
        files_hint=[f.path] if f.path else [],
        contract=ValidationContract(
            task_id="T01",
            assertions=[criterion],
            # FR-803 freezes the contract at planning, before code. Backlog
            # acceptance is the analogous moment: still before any code, with
            # a deterministic producer instead of the planner.
            frozen=True,
        ),
    )

    arch = ArchitectureSpec(
        overview=(
            f"Tidy-up: {title}\n\n{f.detail}\n\nOpened by an E-44 "
            f"tidy-up run from triage finding `{identity}`."
        ),
        decisions=[
            ArchitectureDecision(
                id="D1",
                decision=f"Change only what `{f.rule}` requires"
                + (f", in {f.path}" if f.path else ""),
                rationale="One PR per accepted finding (E-44 D2), so the client "
                "can merge this fix without accepting the others.",
            )
        ],
        affected_modules=[f.path] if f.path else [],
    )

    return SeededWork(arch=arch, plan=ImplementationPlan(tasks=[task]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tidyup_backlog.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/tidyup/ tests/test_tidyup_backlog.py
git commit -m "feat(tidyup): backlog materialization and DevTask authoring (E-44 D1/D2/D7/D10)

mechanical_backlog returns (identity, finding) sorted by identity --
load-bearing, since child workflow ids derive from position and replay
must reproduce them. admitted() reuses E-42's rule verbatim rather than
restating it. seeded_work_for authors one task per finding whose
acceptance criterion names the signal, rule and version that produced it,
so review and QA validate against the finding rather than the harness's
narrative.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: `TidyUpWorkflow`

**Files:**
- Create: `src/sdlc/workflows/tidyup.py`
- Test: `tests/test_tidyup_workflow.py`

**Interfaces:**
- Consumes: `GateHost` (`workflows/gates.py`); `TriageInput`/`TriageWorkflow` (`workflows/triage.py`); `FeatureWorkflow` (Task 4's three-arg `run`); `build_verification_branch`/`VerifyBranchInput` (Task 5); `admitted`/`mechanical_backlog`/`seeded_work_for` (Task 6); `compute_delta` (Task 3).
- Produces: `TidyUpInput`, `FixRunResult`, `TidyUpReport`, `TidyUpWorkflow` (with a `report()` query and a `select_items` signal). Task 8 registers and drives them.

Model `TidyUpWorkflow` on `workflows/triage.py`: same `GateHost` base, same `with workflow.unsafe.imports_passed_through():` block, same per-activity timeout constants at module level.

- [ ] **Step 1: Write the failing test**

Create `tests/test_tidyup_workflow.py`:

```python
"""E-44. Pure helpers directly; sequencing through the workflow, following
tests/test_triage_workflow.py."""

from __future__ import annotations

import pytest

from sdlc.models import GatePolicy
from sdlc.workflows.tidyup import (
    FixRunResult,
    TidyUpInput,
    TidyUpReport,
    branches_to_verify,
    fix_workflow_id,
    reached_a_pr,
)


def test_input_defaults():
    inp = TidyUpInput(repo_dir="/r")
    assert inp.commit == "HEAD"
    assert inp.build_probe is True
    assert inp.max_fix_runs == 10


def test_fix_cfg_disables_the_deploy_gate():
    """D9: feature.py opens the deploy gate BEFORE checking deploy.enabled,
    and the default policy is HARD -- so an unconfigured tidy-up PR would
    park for 48h on a deploy that was never going to run."""
    inp = TidyUpInput(repo_dir="/r")
    assert inp.fix_cfg.gates["deploy"].policy is GatePolicy.OFF
    assert inp.fix_cfg.deploy.enabled is False


@pytest.mark.parametrize(
    "outcome,expected",
    [
        ("deployed:https://example/pr/1", True),
        ("merged-not-deployed:https://example/pr/1", True),
        ("merged-not-deployed:skipped:benchmark-run-has-no-remote", True),
        ("rejected:merge:soft-verdict", False),
        ("rejected:plan", False),
        ("rejected:budget", False),
        ("failed:plan-validation:cycle", False),
        ("", False),
    ],
)
def test_reached_a_pr(outcome, expected):
    """D6 step 6: 'produced a branch worth merging' is read off the return
    string, which is the only thing FeatureWorkflow gives a caller."""
    assert reached_a_pr(outcome) is expected


def test_branches_to_verify_keeps_accepted_order_and_drops_failures():
    runs = [
        FixRunResult(
            identity="a", workflow_id="w-fix-00", outcome="merged-not-deployed:u", branch="b0"
        ),
        FixRunResult(
            identity="b", workflow_id="w-fix-01", outcome="rejected:merge:soft-verdict", branch="b1"
        ),
        FixRunResult(identity="c", workflow_id="w-fix-02", outcome="deployed:u", branch="b2"),
    ]
    assert branches_to_verify(runs) == ["b0", "b2"]


def test_branches_to_verify_drops_a_run_with_no_branch():
    runs = [FixRunResult(identity="a", workflow_id="w", outcome="deployed:u", branch=None)]
    assert branches_to_verify(runs) == []


def test_fix_workflow_id_is_derived_and_stable():
    """D10: no uuid, no clock. Replay must produce the same id."""
    assert fix_workflow_id("tidyup-repo-x", 0) == "tidyup-repo-x-fix-00"
    assert fix_workflow_id("tidyup-repo-x", 7) == "tidyup-repo-x-fix-07"
    assert fix_workflow_id("tidyup-repo-x", 11) == "tidyup-repo-x-fix-11"


def test_report_defaults_are_honest_about_an_unmeasured_after():
    r = TidyUpReport(
        before=None,
        after=None,
        verify_ref=None,
        backlog=[],
        accepted=[],
        deferred=[],
        runs=[],
        deltas=[],
        readiness_before=None,
        readiness_after=None,
    )
    assert r.after is None and r.verify_ref is None
```

> If `TidyUpReport.before` is non-optional in your implementation (it should be
> — a report always has a baseline), drop the last test and instead assert the
> field is required via `pytest.raises(ValidationError)`.

Add the temporal half in the same file:

```python
@pytest.mark.temporal
async def test_not_admitted_returns_the_backlog_and_starts_no_fix_runs():
    """D7: not admitted is not empty-handed. The backlog IS US-8's checkable
    hygiene list, and it lands even when nothing is fixed."""
    report = await _run_tidyup(verdict="not_ready", mechanical=2)
    assert len(report.backlog) == 2
    assert report.accepted == [] and report.runs == []
    assert all(d.state.value == "unverifiable" for d in report.deltas)


@pytest.mark.temporal
async def test_select_items_narrows_the_accepted_set():
    """D8: a signal for content, a gate for the decision."""
    report = await _run_tidyup(verdict="ready", mechanical=3, select=["<second identity>"])
    assert len(report.accepted) == 1


@pytest.mark.temporal
async def test_a_signal_after_the_gate_resolves_does_not_change_what_ran():
    """D8: selection is read once, at decision time."""
    report = await _run_tidyup(
        verdict="ready", mechanical=2, select_after_decision=["<first identity>"]
    )
    assert len(report.accepted) == 2


@pytest.mark.temporal
async def test_max_fix_runs_defers_the_excess_with_the_reason_recorded():
    report = await _run_tidyup(verdict="ready", mechanical=3, max_fix_runs=2)
    assert len(report.runs) == 2
    assert len(report.deferred) == 1
```

> `_run_tidyup` is a local helper you write in this file. Build it by copying
> the `WorkflowEnvironment.start_time_skipping()` + `Worker(...)` block from
> `tests/test_triage_workflow_e2e.py` verbatim, registering `TidyUpWorkflow`,
> `TriageWorkflow` and `FeatureWorkflow` alongside the fake activities in
> `tests/fakes/fake_activities.py`. Stub the fix runs by registering a
> `FeatureWorkflow` whose fake activities return immediately — the assertions
> here are about *sequencing and selection*, not about the fix runs' contents,
> which Task 4 already covers.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tidyup_workflow.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.workflows.tidyup'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/workflows/tidyup.py`:

```python
"""TidyUpWorkflow (E-44) -- Tier 0's fix half.

Assess -> fix -> PROVE. Accepted MECHANICAL findings become governed
brownfield FeatureWorkflow child runs, one PR each (NG5, D2), and triage then
re-runs against a composite verification branch so the before/after delta is
recorded evidence rather than a claim.

No LLM call lives here. Every model call happens inside the child fix runs.

Operator-run only. The fix runs execute the triaged repository's build and
test commands, which is a wider exposure than E-42's build probe alone
(NFR-9). E-57 and E-21 are what remove that debt.
"""

from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel, Field
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..activities import VerifyBranchInput, build_verification_branch
    from ..models import (
        GateConfig,
        GatePolicy,
        GateSettings,
        IdeaBrief,
        PipelineConfig,
        ProjectMode,
    )
    from ..pending import GateContext
    from ..tidyup.backlog import (
        admitted,
        mechanical_backlog,
        seeded_work_for,
    )
    from ..triage.delta import FindingDelta, compute_delta
    from ..triage.models import RepoTriage, Verdict
    from .feature import FeatureWorkflow
    from .gates import GateHost
    from .triage import TriageInput, TriageWorkflow

# Local git only; a retry is free because the branch is force-created.
VERIFY_ACT = dict(
    start_to_close_timeout=timedelta(minutes=10), retry_policy=RetryPolicy(maximum_attempts=3)
)


def _fix_gates() -> dict[str, GateConfig]:
    """D9. feature.py opens the `deploy` gate BEFORE checking
    cfg.deploy.enabled, and PipelineConfig.default_gate_policy is HARD -- so
    an unconfigured tidy-up PR would park for 48 hours on a gate for a deploy
    that was never going to run. Defaulted here rather than reordered in
    feature.py: that ordering is deliberate for feature runs, where the gate
    records an operator's intent independently of deploy configuration.
    """
    cfg = PipelineConfig()
    gates = dict(cfg.gates)
    gates["deploy"] = GateConfig(policy=GatePolicy.OFF)
    return gates


def _default_fix_cfg() -> PipelineConfig:
    cfg = PipelineConfig()
    cfg.gates = _fix_gates()
    return cfg


class TidyUpInput(BaseModel):
    repo_dir: str
    commit: str = "HEAD"
    build_probe: bool = True
    advisory_source: str = "none"
    base_branch: str = "main"
    gates: GateSettings = Field(default_factory=GateSettings)
    fix_cfg: PipelineConfig = Field(default_factory=_default_fix_cfg)
    max_fix_runs: int = 10  # D10: a cap on spend, not on honesty


class FixRunResult(BaseModel):
    identity: str
    workflow_id: str
    outcome: str  # FeatureWorkflow's return string, verbatim
    pr_url: str | None = None
    branch: str | None = None
    merged_into_verify: bool = False


class TidyUpReport(BaseModel):
    before: RepoTriage
    after: RepoTriage | None = None
    verify_ref: str | None = None
    backlog: list[str] = Field(default_factory=list)
    accepted: list[str] = Field(default_factory=list)
    deferred: list[str] = Field(default_factory=list)
    runs: list[FixRunResult] = Field(default_factory=list)
    deltas: list[FindingDelta] = Field(default_factory=list)
    readiness_before: Verdict
    readiness_after: Verdict | None = None


def fix_workflow_id(tidyup_id: str, index: int) -> str:
    """D10: derived, never generated. Replay must produce the same id, and a
    fix run stays identifiable in the Temporal UI."""
    return f"{tidyup_id}-fix-{index:02d}"


def reached_a_pr(outcome: str) -> bool:
    """Whether a fix run produced a branch worth merging into the
    verification tree. The return string is the only thing FeatureWorkflow
    gives a caller, and `deployed:` / `merged-not-deployed:` are the two
    prefixes reachable only after the absolute merge gate passed."""
    return outcome.startswith(("deployed:", "merged-not-deployed:"))


def branches_to_verify(runs: list[FixRunResult]) -> list[str]:
    """Successful branches in accepted order (D6)."""
    return [r.branch for r in runs if r.branch and reached_a_pr(r.outcome)]


def _backlog_summary(pairs, deferred_from: int) -> str:
    """ASCII render for the gate's pending item."""
    lines = []
    for n, (identity, f) in enumerate(pairs):
        mark = "  " if n < deferred_from else "* "
        lines.append(f"{mark}{identity}  [{f.severity}] {f.detail[:90]}")
    tail = (
        "\n\n(* beyond max_fix_runs; deferred with the reason recorded)"
        if len(pairs) > deferred_from
        else ""
    )
    return (
        f"{len(pairs)} mechanically-fixable finding(s). Approving opens "
        f"one PR per item.\n\n" + "\n".join(lines) + tail
    )


@workflow.defn
class TidyUpWorkflow(GateHost):
    def __init__(self) -> None:
        super().__init__()
        self._report: TidyUpReport | None = None
        self._selected: list[str] | None = None

    @workflow.query
    def report(self) -> TidyUpReport | None:
        """The artifact; None until the baseline triage completes."""
        return self._report

    @workflow.signal
    def select_items(self, identities: list[str]) -> None:
        """D8: narrows the backlog before the gate is decided. Unsent means
        all. Read ONCE, at decision time -- a signal arriving afterwards
        cannot retroactively change what ran."""
        self._selected = list(identities)

    async def _triage(self, inp: TidyUpInput, suffix: str, commit: str) -> RepoTriage:
        return await workflow.execute_child_workflow(
            TriageWorkflow.run,
            TriageInput(
                repo_dir=inp.repo_dir,
                commit=commit,
                build_probe=inp.build_probe,
                advisory_source=inp.advisory_source,
                gates=inp.gates,
            ),
            id=f"{workflow.info().workflow_id}-triage-{suffix}",
            task_queue=workflow.info().task_queue,
        )

    async def _fix_run(
        self, inp: TidyUpInput, index: int, identity: str, finding, signal_version: int
    ) -> FixRunResult:
        """One accepted finding -> one governed run -> one PR.

        A child that raises degrades THIS item only, never the tidy-up --
        the shape TriageWorkflow._one established.
        """
        wf_id = fix_workflow_id(workflow.info().workflow_id, index)
        branch = f"sdlc/{wf_id}/integration"
        try:
            outcome = await workflow.execute_child_workflow(
                FeatureWorkflow.run,
                args=[
                    IdeaBrief(
                        title=f"tidy-up: {finding.rule}",
                        description=finding.detail,
                        mode=ProjectMode.BROWNFIELD,
                        repo_url=inp.repo_dir,
                        base_branch=inp.base_branch,
                    ),
                    inp.fix_cfg,
                    seeded_work_for(identity, finding, signal_version),
                ],
                id=wf_id,
                task_queue=workflow.info().task_queue,
            )
        except Exception as e:  # noqa: BLE001
            return FixRunResult(
                identity=identity,
                workflow_id=wf_id,
                outcome=f"failed:{type(e).__name__}: {e}"[:300],
            )
        pr = outcome.split(":", 1)[1] if reached_a_pr(outcome) else None
        return FixRunResult(
            identity=identity,
            workflow_id=wf_id,
            outcome=outcome,
            pr_url=pr,
            branch=branch if reached_a_pr(outcome) else None,
        )

    @workflow.run
    async def run(self, inp: TidyUpInput) -> TidyUpReport:
        self._status = "triaging"
        before = await self._triage(inp, "before", inp.commit)

        versions = {s.signal: s.version for s in before.signals}
        pairs = mechanical_backlog(before)
        backlog = [identity for identity, _ in pairs]

        def _finish(**kw) -> TidyUpReport:
            self._report = TidyUpReport(
                before=before, backlog=backlog, readiness_before=before.readiness.verdict, **kw
            )
            return self._report

        if not admitted(before):
            # D7: not admitted is not empty-handed -- the backlog IS US-8's
            # checkable hygiene list. D5 rule 4 supplies the deltas.
            self._status = "blocked:readiness"
            return _finish(deltas=compute_delta(before, None))

        if not backlog:
            self._status = "tidied:nothing-mechanical"
            return _finish(deltas=compute_delta(before, None))

        self._status = "awaiting:tidy_up"
        decision = await self._gate(
            "tidy_up",
            inp.gates,
            context=GateContext(spec_summary=_backlog_summary(pairs, inp.max_fix_runs)),
        )
        if not decision.approved:
            self._status = "rejected:tidy_up"
            return _finish(deltas=compute_delta(before, None))

        # D8: read the selection ONCE, here.
        chosen = (
            backlog if self._selected is None else [i for i in backlog if i in set(self._selected)]
        )
        accepted = chosen[: inp.max_fix_runs]
        deferred = chosen[inp.max_fix_runs :]
        by_identity = dict(pairs)

        self._status = "fixing"
        runs: list[FixRunResult] = []
        for index, identity in enumerate(accepted):
            finding = by_identity[identity]
            runs.append(
                await self._fix_run(inp, index, identity, finding, versions.get(finding.signal, 0))
            )

        branches = branches_to_verify(runs)
        if not branches:
            # D5 rule 4: nothing to measure, and the report says so.
            self._status = "tidied:no-branches"
            return _finish(
                accepted=accepted, deferred=deferred, runs=runs, deltas=compute_delta(before, None)
            )

        self._status = "verifying"
        verify = await workflow.execute_activity(
            build_verification_branch,
            VerifyBranchInput(
                repo_path=inp.repo_dir,
                base_sha=before.commit_sha,
                tidyup_id=workflow.info().workflow_id,
                branches=branches,
            ),
            **VERIFY_ACT,
        )
        merged = set(verify.merged)
        for r in runs:
            r.merged_into_verify = r.branch in merged
        conflicted = [r.identity for r in runs if r.branch and r.branch not in merged]

        after = await self._triage(inp, "after", verify.head_sha)
        self._status = "tidied"
        return _finish(
            after=after,
            verify_ref=verify.ref,
            accepted=accepted,
            deferred=deferred,
            runs=runs,
            readiness_after=after.readiness.verdict,
            deltas=compute_delta(before, after, conflicted),
        )
```

Two things to check while writing:
- `GateContext`'s field for free text is `spec_summary` in `triage.py`'s usage; confirm against `src/sdlc/pending.py` and use whatever that file defines.
- `FeatureWorkflow`'s integration branch name — read `setup_integration_branch` in `activities.py` and make `branch` above match its actual format exactly. If it is not `sdlc/<run_id>/integration`, use the real one; `IntegrationHandle` is the authority.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tidyup_workflow.py -v`
Expected: PASS on the unit tests.

Run: `python -m pytest tests/test_tidyup_workflow.py -m temporal -v`
Expected: PASS on the four temporal tests.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/tidyup.py tests/test_tidyup_workflow.py
git commit -m "feat(tidyup): TidyUpWorkflow -- assess, fix, prove (E-44)

Baseline triage -> backlog -> tidy_up gate -> N seeded fix runs -> a
composite verification branch -> after-triage -> delta.

Every failure degrades one item, never the run: a child that raises
becomes failed: on that FixRunResult, a merge conflict is recorded and
the remaining branches still merge, and no branches at all yields
after=None with every identity UNVERIFIABLE rather than an empty delta.

Not admitted is not empty-handed -- the backlog is US-8's checkable
hygiene list and lands even when nothing is fixed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Worker registration and the CLI

**Files:**
- Modify: `src/sdlc/worker.py` (workflows list ~line 96, activities list ~line 99)
- Modify: `src/sdlc/cli.py` (module docstring ~line 15, parser ~line 203, dispatch ~line 354)
- Test: `tests/test_tidyup_cli_wiring.py`

**Interfaces:**
- Consumes: `TidyUpWorkflow`, `TidyUpInput` (Task 7); `build_verification_branch` (Task 5).
- Produces: `tidyup_workflow_id(repo, now=None) -> str` in `cli.py`, and the `tidyup` / `tidyup select` / `tidyup show` verbs.

`sdlc approve --id <tidyup-wf> --gate tidy_up` needs **no change** — `channels/transport.py` resolves and submits by *name* and imports nothing from `FeatureWorkflow`, as its docstring states. Confirm this with a test rather than assuming it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_tidyup_cli_wiring.py`:

```python
"""E-44's operator surface. Mirrors tests/test_triage_cli_wiring.py."""

from datetime import datetime, timezone

import pytest

from sdlc.cli import tidyup_workflow_id


def test_workflow_id_is_per_run_not_per_repository():
    """Same reason triage_workflow_id carries a stamp (E-42 D5): Temporal
    refuses to start a workflow whose id is already RUNNING, so a bare
    tidyup-<slug> would let one tidy-up parked on the gate block the next."""
    now = datetime(2026, 8, 9, 10, 15, 0, tzinfo=timezone.utc)
    assert tidyup_workflow_id("/x/my-repo", now) == "tidyup-my-repo-20260809T101500Z"


def test_workflow_id_slugifies_the_basename():
    now = datetime(2026, 8, 9, 10, 15, 0, tzinfo=timezone.utc)
    assert tidyup_workflow_id("/x/My Repo!", now).startswith("tidyup-my-repo-")


def test_two_ids_for_one_repo_differ():
    a = tidyup_workflow_id("/x/r", datetime(2026, 8, 9, 10, 15, 0, tzinfo=timezone.utc))
    b = tidyup_workflow_id("/x/r", datetime(2026, 8, 9, 10, 16, 0, tzinfo=timezone.utc))
    assert a != b


def test_child_triage_ids_do_not_collide_with_a_standalone_triage():
    """TidyUpWorkflow derives its children as <id>-triage-before/-after."""
    now = datetime(2026, 8, 9, 10, 15, 0, tzinfo=timezone.utc)
    assert not tidyup_workflow_id("/x/r", now).startswith("triage-")


def test_worker_registers_the_workflow_and_the_activity():
    import inspect

    from sdlc import worker

    src = inspect.getsource(worker)
    assert "TidyUpWorkflow" in src
    assert "build_verification_branch" in src


def test_approve_reaches_a_tidyup_workflow_unchanged():
    """channels/transport.py resolves and submits BY NAME and imports nothing
    from FeatureWorkflow -- so the existing approve verb already works against
    TidyUpWorkflow. This test exists so a future refactor cannot quietly
    break that."""
    import inspect

    from sdlc.channels import transport

    src = inspect.getsource(transport)
    assert "FeatureWorkflow" not in src


@pytest.mark.parametrize(
    "argv,expected",
    [
        (["tidyup", "--repo", "/x/r"], {"repo": "/x/r", "max_fix_runs": 10}),
        (["tidyup", "--repo", "/x/r", "--max-fix-runs", "3"], {"repo": "/x/r", "max_fix_runs": 3}),
    ],
)
def test_parser_accepts_the_tidyup_flags(argv, expected, monkeypatch):
    """Built by calling the same parser main() builds -- extract it into a
    module-level build_parser() if it is still inline in main()."""
    from sdlc.cli import build_parser

    args = build_parser().parse_args(argv)
    assert args.cmd == "tidyup"
    assert args.repo == expected["repo"]
    assert args.max_fix_runs == expected["max_fix_runs"]


def test_parser_accepts_select_and_show():
    from sdlc.cli import build_parser

    a = build_parser().parse_args(["tidyup", "select", "--id", "w", "--identities", "a,b"])
    assert a.tidyup_cmd == "select" and a.identities == "a,b"
    b = build_parser().parse_args(["tidyup", "show", "--id", "w"])
    assert b.tidyup_cmd == "show"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tidyup_cli_wiring.py -v`
Expected: FAIL — `ImportError: cannot import name 'tidyup_workflow_id'`

- [ ] **Step 3: Write minimal implementation**

**3a.** `src/sdlc/worker.py` — add `TidyUpWorkflow` to the `workflows=[...]` list and `build_verification_branch` to `activities=[...]`, with the matching imports at the top of the file (`from .workflows.tidyup import TidyUpWorkflow`, and `build_verification_branch` added to the existing `from .activities import (...)` block).

**3b.** `src/sdlc/cli.py` — if the parser is still built inline in `main()`, extract it into a module-level `def build_parser() -> argparse.ArgumentParser:` that returns `p`, and have `main()` call `args = build_parser().parse_args()`. This is a pure move; the test above depends on it.

Add beside `triage_workflow_id`:

```python
def tidyup_workflow_id(repo: str, now: datetime | None = None) -> str:
    """A distinct id per tidy-up RUN, for the same reason triage_workflow_id
    carries a stamp (E-42 D5): Temporal refuses to start a workflow whose id
    is already RUNNING, so a bare `tidyup-<slug>` would let one tidy-up parked
    on the gate block the next one for that repository."""
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return f"tidyup-{slug(os.path.basename(repo))}-{stamp}"
```

Add the parser block beside the `triage` one:

```python
tu = sub.add_parser("tidyup")
tusub = tu.add_subparsers(dest="tidyup_cmd")
tu.add_argument("--repo", help="path to an already-cloned repository")
tu.add_argument("--commit", default="HEAD")
tu.add_argument("--no-build-probe", action="store_true", dest="no_build_probe")
tu.add_argument("--advisory-source", default="none")
tu.add_argument("--base-branch", default="main", dest="base_branch")
tu.add_argument(
    "--max-fix-runs",
    type=int,
    default=10,
    dest="max_fix_runs",
    help="cap on fix runs; the excess is deferred and recorded, never dropped silently",
)
tus = tusub.add_parser("select")
tus.add_argument("--id", required=True)
tus.add_argument(
    "--identities",
    required=True,
    help="comma-separated finding identities to fix; omit the verb entirely to fix all of them",
)
tush = tusub.add_parser("show")
tush.add_argument("--id", required=True)
```

Add the dispatch beside the `triage` blocks, **before** the
`handle = client.get_workflow_handle_for(FeatureWorkflow.run, args.id)` line:

```python
if args.cmd == "tidyup" and args.tidyup_cmd == "show":
    handle = client.get_workflow_handle(args.id)
    report = await handle.query(TidyUpWorkflow.report)
    print("no tidy-up report yet" if report is None else report.model_dump_json(indent=2))
    return

if args.cmd == "tidyup" and args.tidyup_cmd == "select":
    handle = client.get_workflow_handle(args.id)
    identities = [s.strip() for s in args.identities.split(",") if s.strip()]
    await handle.signal(TidyUpWorkflow.select_items, identities)
    print(
        f"selected {len(identities)} finding(s); "
        f"approve with: sdlc approve --id {args.id} --gate tidy_up"
    )
    return

if args.cmd == "tidyup":
    if not args.repo:
        raise SystemExit("tidyup requires --repo")
    repo = os.path.abspath(args.repo)
    wf_id = tidyup_workflow_id(repo)
    handle = await client.start_workflow(
        TidyUpWorkflow.run,
        TidyUpInput(
            repo_dir=repo,
            commit=args.commit,
            build_probe=not args.no_build_probe,
            advisory_source=args.advisory_source,
            base_branch=args.base_branch,
            max_fix_runs=args.max_fix_runs,
        ),
        id=wf_id,
        task_queue=TASK_QUEUE,
    )
    print(f"started {handle.id}")
    print(
        "NOTE: the build probe AND the fix runs execute this "
        "repository's own code as the worker user. Operator-run only "
        "(NFR-9)."
    )
    return
```

Import at the top: `from .workflows.tidyup import TidyUpInput, TidyUpWorkflow`.

Add `tidyup` to `_needs_temporal_client`'s command set — check how `triage` is listed there and follow it exactly.

Update the module docstring's usage block with:

```
  python -m sdlc.cli tidyup --repo /path/to/repo
  python -m sdlc.cli tidyup select --id tidyup-myrepo-20260809T101500Z --identities a,b
  python -m sdlc.cli tidyup show --id tidyup-myrepo-20260809T101500Z
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tidyup_cli_wiring.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Verify the whole suite**

Run: `python -m pytest tests/ -q`
Then: `python -m pytest -m temporal -q`
Expected: PASS. In particular `tests/test_triage_cli_wiring.py` must still pass — the `build_parser` extraction is a pure move.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/worker.py src/sdlc/cli.py tests/test_tidyup_cli_wiring.py
git commit -m "feat(cli): sdlc tidyup / select / show (E-44 D8)

Per-run workflow ids for the same reason triage carries a stamp: a
tidy-up parked on its gate must not block the next one.

approve needs no change -- channels/transport.py resolves and submits by
name and imports nothing from FeatureWorkflow, so the existing verb
already reaches TidyUpWorkflow. A test pins that so a refactor cannot
quietly break it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: Tracker and documentation

**Files:**
- Modify: `ROADMAP.md`
- Modify: `docs/superpowers/specs/2026-08-09-tidy-up-fix-runs-and-re-triage-design.md` (status line)

**Interfaces:**
- Consumes: everything above, verified green.
- Produces: nothing code depends on.

Do this task **only after** the full suite is green. The tracker's method line is *"Every FR / NFR / SC / US / ADR checked against actual code, not against prior audit claims"* — so verify each claim below against the code before marking it.

- [ ] **Step 1: Verify the claims**

Run: `python -m pytest tests/ -q && python -m pytest -m temporal -q`
Expected: PASS. Record the counts; they go in the commit body.

- [ ] **Step 2: Update `ROADMAP.md`**

Make these edits:

- Line ~6, "Last verified": add `E-44 against src/sdlc/{tidyup,workflows/tidyup.py,triage/delta.py} + pytest -m temporal` with today's date, keeping the existing entries.
- Line ~100, **P5**: change `[ ]` to `[x]` and rewrite the note — the exit criterion is met, E-40…E-44 all land.
- Line ~207, **FR-904**: `[ ]` → `[x]`, note naming `TidyUpWorkflow`, the seeded entry point, and the verification-branch delta.
- Line ~296, **US-8**: `[ ] ⚠️` → `[x]`; the checkable-hygiene-list half is the backlog, which lands even when a repo is not admitted.
- Line ~297, **US-9**: `[ ]` → `[x]`.
- §10's **E-44** bullet: `[ ]` → `[x]`, with the spec and plan paths, and the three sub-decisions the one-line description did not contain: `SeededWork` (D1), `UNVERIFIABLE` (D5), the verification branch (D6).
- §15 item 2: mark the chain closed.
- **FR-915**: add a line noting the delta is a second consumer of the `not_collected` discipline.
- **NFR-9**: extend — the fix runs execute the repository's build and test commands, a wider exposure than the build probe alone.
- §1 stage 0 (**intake**) and **FR-102**: leave unchanged. E-44 uses `ProjectMode.BROWNFIELD` but adds **no** classify logic or `CodebaseMap`; claiming otherwise would be exactly the kind of drift the 2026-07-16 ADR-6 correction was written about.

- [ ] **Step 3: Update the spec status**

Change the spec's `| Status | Designed |` row to `| Status | Implemented |`.

- [ ] **Step 4: Commit**

```bash
git add ROADMAP.md docs/superpowers/specs/2026-08-09-tidy-up-fix-runs-and-re-triage-design.md
git commit -m "docs: E-44 lands -- FR-904, US-8, US-9 close, P5 reaches its exit

Tier 0 is complete: E-40/E-41/E-42/E-43/E-44 all landed. One unfamiliar
repository can be triaged, a mechanical backlog fixed through governed
runs, and the before/after delta recorded.

FR-102 and DAG stage 0 deliberately unchanged: E-44 sets
ProjectMode.BROWNFIELD but adds no classify logic and no CodebaseMap.
Marking them would be the drift the 2026-07-16 ADR-6 correction was
written about.

NFR-9 exposure widened and recorded: the fix runs execute the triaged
repository's build and test commands, not just the build probe.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**

| Spec item | Task |
|---|---|
| D1 seeded entry point | 4 |
| D2 one PR per finding | 6 (one task per `SeededWork`), 7 (one child per identity) |
| D3 identity | 1, 2 |
| D4 `compute_delta` sole producer | 3 |
| D5 five honesty rules | 3 (rules 1, 2, 4, 5), 3 + 7 (rule 3: `conflicted` computed in 7, applied in 3) |
| D6 verification branch | 5, 7 |
| D7 admission | 6 (`admitted`), 7 |
| D8 `select_items` + gate | 7, 8 |
| D9 deploy gate OFF | 7 (`_default_fix_cfg`) |
| D10 serial, capped, derived ids | 6 (sorted backlog), 7 |
| §3 contracts | 1, 3, 4, 7 |
| §5 error handling | 3, 5, 7 |
| §6 testing | every task |
| §8 what this closes | 9 |

**Type consistency checked:** `finding_identity(f)` takes one argument everywhere (Tasks 1, 2, 3, 6). `compute_delta(before, after, conflicted)` — three parameters at every call site (Tasks 3, 7). `FeatureWorkflow.run(idea, cfg, seeded)` — Task 4 defines it, Task 7 calls it with `args=[…]` in that order, Task 4's `test_run_accepts_seeded_as_a_third_argument` pins it. `VerifyResult` fields `ref`/`head_sha`/`merged`/`conflicted` — Task 5 defines, Task 7 reads all four. `TidyUpReport` fields match between Task 7's definition and Task 8's `show`.

**Two known integration points the implementer must read rather than assume**, both flagged inline: `GateContext`'s free-text field name (`src/sdlc/pending.py`), and `setup_integration_branch`'s actual branch-name format (`src/sdlc/activities.py`) — Task 7's `branch` string must match it exactly or `branches_to_verify` hands `build_verification_branch` a ref that does not exist.
