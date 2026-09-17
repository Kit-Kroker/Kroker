# Herdr v3 (spec-kit crew) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the superpowers process spine of the herdr crew with GitHub spec-kit: scaffold `.specify/` in the repo, build the v3 crew library + five mode tabs (constitution / plan / exec / bug / assess), repoint keybindings, and rewrite the orchestration protocol/manual.

**Architecture:** Approach C from the spec — a shared bash lib (`_crew.sh`) that builds herdr tabs from per-mode `layout.sh` declarations and sends per-seat briefs from `briefs.md` files; thin per-mode entry scripts in `.workspace/bin/`; briefs drive `/speckit-*` skills of each seat's agent. Layout is bash (it *is* layout code); briefs are markdown (editable without bash). One refinement over the spec's file map: each mode is a directory `modes/<mode>/{layout.sh,briefs.md}` instead of a single `.md` with a header block — same intent, no mini-DSL parser.

**Tech Stack:** bash (Git Bash on Windows), herdr 0.9.0 CLI, specify-cli 0.11.3, spec-kit SDD + bug + assess extensions.

**Spec:** `docs/superpowers/specs/2026-09-17-herdr-v3-speckit-setup-design.md`

## Global Constraints

- Working directory for every command: `D:\own\Kroker` (PowerShell 5.1 host unless noted).
- **Bash means Git Bash** (`"C:\Program Files\Git\bin\bash.exe"`), never the WSL `bash.exe` on PATH. From PowerShell invoke as `& "C:\Program Files\Git\bin\bash.exe" -lc "<cmd>"`.
- `.workspace/` is **gitignored by design** — Tasks 2–6 have no commit steps. The only repo commit is the spec-kit scaffold (Task 1). herdr `config.toml` lives outside the repo.
- Commit messages: subject + body only, **no attribution trailers of any kind** (no `Co-Authored-By:`, no session links).
- No heredocs for multi-line content in PowerShell-adjacent paths; commit via `git commit -F <msgfile>` where a body is needed.
- Installed and verified: `specify 0.11.3`, `uv`, `herdr 0.9.0`. `shellcheck` is NOT installed — syntax checks are `bash -n` only.
- File-size ceiling 1000 lines applies to everything committed under `docs/`, `src/`, root `*.md` — including this plan.
- Brief texts below are complete; every prompt sent to a seat gets the stale-draft tail appended automatically by the lib (do not duplicate it inside briefs).

---

### Task 1: spec-kit scaffold in the repo

**Files:**
- Create: `.specify/**` (via `specify init`)
- Create: speckit command/skill files under `.claude/` and `.opencode/` (via `specify integration install`)
- Create: extension artifacts for bug + assess (via `specify extension add`)

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `/speckit-*` skills available to claude and opencode seats; `.specify/specs|bugs|assessments/` artifact roots; `.specify/templates/checklists/` used by reviewer briefs in Task 3.

- [ ] **Step 1: Init spec-kit with the claude integration**

Run (PowerShell, from `D:\own\Kroker`):

```
specify init . --integration claude
```

Expected: `.specify/` created with `specs/`, `templates/`, `scripts/`, `memory/`; exit 0. If init prompts interactively (git hooks, etc.), answer No to git-hook installation — crew commits stay manual by protocol.

- [ ] **Step 2: Add opencode and gemini integrations**

```
specify integration install opencode
specify integration install gemini
```

Expected: exit 0 both; `specify integration status` lists three installed integrations. Gemini integration is best-effort for the `agy` seats — skeptic/advisor seats never invoke `/speckit-*` (they work from briefs), so failure here is not a blocker; record and continue.

- [ ] **Step 3: Add bug and assess extensions**

```
specify extension add bug
specify extension add assess
```

Expected: exit 0 both; `.specify/` (or extension dirs) gains bug (`assess → fix → test`) and assess (`intake → research → define → shape → decide`) skill files.

- [ ] **Step 4: Verify scaffold acceptance**

Run:

```
specify --version
git check-ignore .specify ; if ($LASTEXITCODE -eq 0) { echo "IGNORED - BAD" } else { echo "tracked - OK" }
python scripts/check_file_size.py
```

Expected: `specify 0.11.3`; `.specify` NOT ignored (rc 1 → "tracked - OK"); file-size check passes. Then enumerate speckit-created agent files:

```
git status --porcelain
```

Expected: new untracked paths containing `speckit` under `.claude/` (commands or skills) and `.opencode/`, plus `.specify/`.

- [ ] **Step 5: Commit exactly the scaffold**

Stage only speckit-generated paths (adjust the `.claude/` / `.opencode/` subpaths to what Step 4 actually listed — never `git add .claude` wholesale, that directory holds local-only skills):

```
git add .specify
git add .claude/skills/speckit-constitution .claude/skills/speckit-specify .claude/skills/speckit-plan .claude/skills/speckit-tasks .claude/skills/speckit-implement .claude/skills/speckit-converge
git add .opencode
```

(If claude integration installed commands instead of skills, stage the actual `speckit-*.md` paths shown by `git status`.) Then:

```
git commit -m "chore: scaffold spec-kit (SDD + bug + assess) for crew v3"
```

Expected: pre-commit hooks pass; one commit containing `.specify/` + speckit agent files only.

---

### Task 2: crew lib — parsing and brief composition (TDD)

**Files:**
- Create: `.workspace/crew/v3/lib/_crew.sh`
- Create: `.workspace/crew/v3/tests/run-tests.sh`
- Create: `.workspace/crew/v3/tests/fixture/briefs.md`

**Interfaces:**
- Consumes: `.workspace/bin/_json.sh` (existing v2 helper: `jget`, `focused_workspace_id`).
- Produces (sourced API used by tests, mode layouts, and Task 4 entries):
  - `PROMPT_TAIL` — string constant appended to every crew prompt.
  - `build_pane_ops` — fills global array `OPS=("name panespec" ...)` from `SEATS=()` in SEATS order.
  - `extract_brief <briefs.md> <seat>` — prints the `## seat: <name>` section body (blank-trimmed), rc 1 if absent.
  - `validate_mode <mode-dir>` — rc 0 iff every declared seat has a brief section and section count == seat count.
  - `crew_compose_brief <text>` — prints `<text>` + blank line + `PROMPT_TAIL`.
  - `crew_build_tab`, `crew_send_briefs <mode-dir> [lead-task]`, `crew_run <mode> [task-brief] [--layout-only]` — side-effectful; built in this task, live-tested in Task 7.
  - Mode contract consumed by the lib: `layout.sh` sets `TAB_LABEL`, `LEAD_SEAT`, `SEATS=( "name|kind|panespec|extra-args" ... )`, `SHIM_SEATS=(...)`. `panespec` is `root`, `right:<of-seat>:<ratio>`, or `down:<of-seat>:<ratio>` (parent must be declared earlier).

- [ ] **Step 1: Write the failing tests**

Create `.workspace/crew/v3/tests/fixture/briefs.md`:

```markdown
## seat: planner
Plan the thing.

## seat: advisor
Advise on tradeoffs.

## seat: skeptic
Attack the plan.

## seat: reviewer
Judge the plan.
```

Create `.workspace/crew/v3/tests/run-tests.sh`:

```bash
#!/usr/bin/env bash
# Unit tests for _crew.sh pure logic. Run via Git Bash:
#   .workspace/crew/v3/tests/run-tests.sh
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CREW_V3_DIR="$(cd "$HERE/.." && pwd)"
# shellcheck source=../lib/_crew.sh
source "$CREW_V3_DIR/lib/_crew.sh"

fails=0
ok()   { echo "ok: $1"; }
fail() { echo "FAIL: $1: got [$2] want [$3]"; fails=$((fails+1)); }
assert_eq() { if [ "$2" = "$3" ]; then ok "$1"; else fail "$1" "$2" "$3"; fi; }

# --- build_pane_ops ---
TAB_LABEL=fixture; LEAD_SEAT=planner
SEATS=(
  "planner|claude|root|--permission-mode acceptEdits"
  "advisor|claude|right:planner:0.5|--permission-mode acceptEdits"
  "skeptic|agy|down:advisor:0.33|--dangerously-skip-permissions"
  "reviewer|opencode|down:skeptic:0.5|"
)
SHIM_SEATS=()
build_pane_ops
assert_eq "ops count" "${#OPS[@]}" "4"
assert_eq "op root" "${OPS[0]}" "planner root"
assert_eq "op split right" "${OPS[1]}" "advisor right:planner:0.5"
assert_eq "op split down chain" "${OPS[3]}" "reviewer down:skeptic:0.5"

# --- extract_brief ---
assert_eq "advisor brief body" "$(extract_brief "$HERE/fixture/briefs.md" advisor)" "Advise on tradeoffs."
assert_eq "missing seat rc" "$(extract_brief "$HERE/fixture/briefs.md" ghost >/dev/null 2>&1; echo $?)" "1"

# --- validate_mode ---
if validate_mode "$HERE/fixture" 2>/dev/null; then ok "fixture validates"; else fail "fixture validates" "rc!=0" "rc=0"; fi

# --- crew_compose_brief ---
assert_eq "compose appends tail" "$(crew_compose_brief Hi)" "Hi

$PROMPT_TAIL"

# --- every shipped mode validates (Task 3 fills them in) ---
for mode_dir in "$CREW_V3_DIR"/modes/*/; do
  mode="$(basename "$mode_dir")"
  (
    source "$mode_dir/layout.sh"
    build_pane_ops
    validate_mode "$mode_dir"
  ) 2>/dev/null && ok "mode $mode validates" || { echo "FAIL: mode $mode does not validate"; fails=$((fails+1)); }
done

if [ "$fails" -eq 0 ]; then echo "ALL PASS"; else echo "$fails FAILURES"; exit 1; fi
```

- [ ] **Step 2: Run tests to verify they fail**

```
& "C:\Program Files\Git\bin\bash.exe" .workspace/crew/v3/tests/run-tests.sh
```

Expected: FAIL — `no such file or directory` sourcing `../lib/_crew.sh` (exit non-zero).

- [ ] **Step 3: Implement `_crew.sh`**

Create `.workspace/crew/v3/lib/_crew.sh`:

```bash
#!/usr/bin/env bash
# _crew.sh — herdr v3 crew lib. Builds a mode tab, starts seats, sends briefs.
# Modes live in ../modes/<mode>/{layout.sh,briefs.md}; entries in .workspace/bin
# exec this file with a mode name. Source-safe: tests source it directly.
set -euo pipefail

CREW_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CREW_V3_DIR="$(cd "$CREW_LIB_DIR/.." && pwd)"
WS_DIR="$(cd "$CREW_V3_DIR/../.." && pwd)"
WS_BIN="$WS_DIR/bin"
# shellcheck source=../../bin/_json.sh
source "$WS_BIN/_json.sh"

PROMPT_TAIL="— disregard any stale partial draft in your input box; this message supersedes it."

build_pane_ops() { # SEATS[] -> OPS[] ("name panespec", SEATS order)
  OPS=()
  local line name pane_spec
  for line in "${SEATS[@]}"; do
    local IFS='|'
    read -r name _kind pane_spec _extra <<<"$line"
    OPS+=("$name $pane_spec")
  done
}

extract_brief() { # <briefs.md> <seat> -> trimmed section body; rc 1 if absent
  local file="$1" seat="$2" out
  out="$(awk -v s="$seat" '
    $0 == "## seat: " s { found = 1; next }
    found && /^## seat: / { exit }
    found { print }
  ' "$file")" || true
  out="${out#"${out%%[![:space:]]*}"}"
  out="${out%"${out##*[![:space:]]}"}"
  [ -n "$out" ] && printf '%s\n' "$out" || return 1
}

validate_mode() { # <mode-dir>: every seat briefed, no orphan sections
  local dir="$1" name _ps declared=0 found
  for op in "${OPS[@]}"; do
    read -r name _ps <<<"$op"
    declared=$((declared + 1))
    extract_brief "$dir/briefs.md" "$name" >/dev/null ||
      { echo "validate_mode: no brief for seat '$name'" >&2; return 1; }
  done
  found="$(grep -c '^## seat: ' "$dir/briefs.md")" || true
  [ "$found" -eq "$declared" ] ||
    { echo "validate_mode: $found brief sections vs $declared seats" >&2; return 1; }
}

crew_compose_brief() { printf '%s\n\n%s\n' "$1" "$PROMPT_TAIL"; }

crew_prompt_seat() { # <seat> <body> — dispatch without --wait (protocol rule)
  herdr agent prompt "${SEAT_PREFIX:-}$1" "$(crew_compose_brief "$2")" >/dev/null
}

seed_shim() { # <pane> — glm-shim PATH seed, v2 mechanics verbatim
  local shim_win
  shim_win="$(cygpath -w "$WS_BIN/glm-shim")"
  MSYS_NO_PATHCONV=1 herdr pane run "$1" "\$env:PATH = \"$shim_win;\" + \$env:PATH"
}

crew_build_tab() { # -> TAB_ID, PANE_OF (global assoc); echoes nothing
  local workspace_id
  workspace_id="$(focused_workspace_id)"
  [ -n "$workspace_id" ] || { echo "_crew: no focused herdr workspace (is a herdr client attached?)" >&2; exit 1; }
  local tab_resp root_pane line name kind pane_spec extra of ratio resp
  tab_resp="$(herdr tab create --workspace "$workspace_id" --cwd "$PWD" --label "$TAB_LABEL" --no-focus)"
  TAB_ID="$(jget "['result']['tab']['tab_id']" <<<"$tab_resp")"
  root_pane="$(jget "['result']['root_pane']['pane_id']" <<<"$tab_resp")"
  declare -gA PANE_OF=()
  for line in "${SEATS[@]}"; do
    local IFS='|'
    read -r name _kind pane_spec _extra <<<"$line"
    case "$pane_spec" in
      root) PANE_OF[$name]="$root_pane" ;;
      right:*|down:*)
        of="${pane_spec#*:}"; of="${of%%:*}"; ratio="${pane_spec##*:}"
        resp="$(herdr pane split --pane "${PANE_OF[$of]}" --direction "${pane_spec%%:*}" --ratio "$ratio" --cwd "$PWD" --no-focus)"
        PANE_OF[$name]="$(jget "['result']['pane']['pane_id']" <<<"$resp")" ;;
      *) echo "_crew: bad pane spec '$pane_spec' for seat '$name'" >&2; exit 1 ;;
    esac
  done
  for s in "${SHIM_SEATS[@]}"; do seed_shim "${PANE_OF[$s]}"; done
  for line in "${SEATS[@]}"; do
    local IFS='|'
    read -r name kind _ps extra <<<"$line"
    if [ -n "$extra" ]; then
      # shellcheck disable=SC2086
      herdr agent start "${SEAT_PREFIX:-}$name" --kind "$kind" --pane "${PANE_OF[$name]}" -- $extra >/dev/null
    else
      herdr agent start "${SEAT_PREFIX:-}$name" --kind "$kind" --pane "${PANE_OF[$name]}" >/dev/null
    fi
    herdr pane rename "${PANE_OF[$name]}" "$name" >/dev/null
  done
}

crew_send_briefs() { # <mode-dir> [lead-task]
  local dir="$1" lead_task="${2:-}" line name body
  for line in "${SEATS[@]}"; do
    local IFS='|'
    read -r name _kind _ps _extra <<<"$line"
    body="$(extract_brief "$dir/briefs.md" "$name")" || continue
    if [ -n "$lead_task" ] && [ "$name" = "$LEAD_SEAT" ]; then
      body="$body

TASK BRIEF:
$lead_task"
    fi
    crew_prompt_seat "$name" "$body"
  done
}

crew_run() {
  local mode="${1:?usage: _crew.sh <mode> [task-brief] [--layout-only]}"
  shift || true
  local layout_only=0 task="" a
  for a in "$@"; do
    case "$a" in
      --layout-only) layout_only=1 ;;
      *) task="$a" ;;
    esac
  done
  local mode_dir="$CREW_V3_DIR/modes/$mode"
  [ -f "$mode_dir/layout.sh" ] ||
    { echo "_crew: unknown mode '$mode' (no $mode_dir/layout.sh)" >&2; exit 1; }
  command -v specify >/dev/null 2>&1 ||
    { echo "_crew: specify CLI not on PATH — uv tool install specify-cli" >&2; exit 1; }
  [ -d "$WS_DIR/.specify" ] ||
    { echo "_crew: .specify/ missing — run: specify init . --integration claude" >&2; exit 1; }
  # shellcheck source=/dev/null
  source "$mode_dir/layout.sh"
  build_pane_ops
  validate_mode "$mode_dir"
  crew_build_tab
  if [ "$layout_only" -eq 0 ]; then crew_send_briefs "$mode_dir" "$task"; fi
  local line name map=""
  for line in "${SEATS[@]}"; do
    local IFS='|'
    read -r name _k _p _e <<<"$line"
    map+=" $name=${PANE_OF[$name]}"
  done
  echo "v3 $mode tab ready: tab=$TAB_ID$map"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then crew_run "$@"; fi
```

- [ ] **Step 4: Run tests to verify lib logic passes (mode loop still red)**

```
& "C:\Program Files\Git\bin\bash.exe" .workspace/crew/v3/tests/run-tests.sh
```

Expected: all `ok:` lines pass EXCEPT the shipped-mode loop reports 5 FAILs (`modes/*/` empty) — this is the red state for Task 3. If pure-logic tests fail, fix `_crew.sh` before proceeding.

---

### Task 3: five modes — layouts and briefs

**Files:**
- Create: `.workspace/crew/v3/modes/constitution/layout.sh` + `briefs.md`
- Create: `.workspace/crew/v3/modes/plan/layout.sh` + `briefs.md`
- Create: `.workspace/crew/v3/modes/exec/layout.sh` + `briefs.md`
- Create: `.workspace/crew/v3/modes/bug/layout.sh` + `briefs.md`
- Create: `.workspace/crew/v3/modes/assess/layout.sh` + `briefs.md`

**Interfaces:**
- Consumes: mode contract from Task 2 (`TAB_LABEL`, `LEAD_SEAT`, `SEATS`, `SHIM_SEATS`; `## seat: <name>` brief sections).
- Produces: five valid modes consumed by Task 4 entries; `.specify/...` paths per spec §3.

- [ ] **Step 1: Write mode layouts**

`.workspace/crew/v3/modes/constitution/layout.sh`:

```bash
TAB_LABEL=constitution
LEAD_SEAT=planner
SEATS=(
  "planner|claude|root|--permission-mode acceptEdits"
  "advisor|claude|right:planner:0.5|--permission-mode acceptEdits"
  "skeptic|agy|down:advisor:0.33|--dangerously-skip-permissions"
  "reviewer|opencode|down:skeptic:0.5|"
)
SHIM_SEATS=()
```

`.workspace/crew/v3/modes/plan/layout.sh`:

```bash
TAB_LABEL=plan
LEAD_SEAT=planner
SEATS=(
  "planner|claude|root|--permission-mode acceptEdits"
  "advisor|claude|right:planner:0.5|--permission-mode acceptEdits"
  "skeptic|agy|down:advisor:0.33|--dangerously-skip-permissions"
  "reviewer|opencode|down:skeptic:0.5|"
)
SHIM_SEATS=()
```

`.workspace/crew/v3/modes/exec/layout.sh`:

```bash
TAB_LABEL=exec
LEAD_SEAT=executor
SEATS=(
  "executor|opencode|root|"
  "qa-happy|claude|right:executor:0.5|--permission-mode acceptEdits"
  "reviewer|agy|down:qa-happy:0.4|--dangerously-skip-permissions"
  "scribe|claude|down:reviewer:0.5|--permission-mode acceptEdits"
  "qa-chaos|claude|right:qa-happy:0.5|--permission-mode acceptEdits"
)
SHIM_SEATS=(qa-happy qa-chaos)
```

`.workspace/crew/v3/modes/bug/layout.sh`:

```bash
TAB_LABEL=bug
LEAD_SEAT=bug-lead
SEATS=(
  "bug-lead|opencode|root|"
  "qa-happy|claude|right:bug-lead:0.5|--permission-mode acceptEdits"
  "reviewer|agy|down:qa-happy:0.4|--dangerously-skip-permissions"
  "qa-chaos|claude|right:qa-happy:0.5|--permission-mode acceptEdits"
)
SHIM_SEATS=(qa-happy qa-chaos)
```

`.workspace/crew/v3/modes/assess/layout.sh`:

```bash
TAB_LABEL=assess
LEAD_SEAT=assessor
SEATS=(
  "assessor|claude|root|--permission-mode acceptEdits"
  "advisor|claude|right:assessor:0.5|--permission-mode acceptEdits"
  "skeptic|agy|down:advisor:0.5|--dangerously-skip-permissions"
)
SHIM_SEATS=()
```

- [ ] **Step 2: Write constitution briefs**

`.workspace/crew/v3/modes/constitution/briefs.md`:

```markdown
## seat: planner
You are the CONSTITUTION AUTHOR for this repo (spec-kit SDD).
1. Run /speckit-constitution with this seed: derive the project constitution
   from the repo's own binding rules — AGENTS.md (stage seams, cross-stage
   call ban, producer-owns-artifacts, worktree norm, 1000-line file ceiling
   via scripts/check_file_size.py), the no-attribution-trailers commit rule,
   verify-before-claiming (rerun pytest/ruff/mypy/file-size yourself), and
   git commit -F <msgfile> discipline (no heredocs).
2. Consult 'advisor' (herdr agent prompt advisor "..." --wait) on phrasing
   and what to leave OUT — a constitution is small and enforceable, not a
   restatement of every rule.
3. Before locking any principle, run it past 'skeptic'
   (herdr agent prompt skeptic "..." --wait); address vagueness with
   concrete, checkable formulations.
4. Do not save until 'reviewer' replies approve; the orchestrator then
   brings the constitution to the USER GATE — it lands only with your
   (the human's) approval.

## seat: advisor
You are the CONSTITUTION ADVISOR. Help the planner phrase principles as
small, enforceable rules; push back on restating whole documents; suggest
omissions. Consultation only — never edit files.

## seat: skeptic
You are the CONSTITUTION SKEPTIC. Attack every draft principle: is it
mechanically checkable or clearly advisory? Does it conflict with
AGENTS.md/CLAUDE.md or duplicate them? Demand concrete reformulations.
Never edit files.

## seat: reviewer
You are the CONSTITUTION REVIEWER. Validate the final draft: testable,
non-overlapping, no contradictions with existing repo rules, at most ~10
principles. Reply exactly 'approve' or 'fixes-needed' with reasons.
```

- [ ] **Step 3: Write plan briefs**

`.workspace/crew/v3/modes/plan/briefs.md`:

```markdown
## seat: planner
You are the SPEC LEAD for spec-kit SDD (specify → plan → tasks).
1. Run /speckit-specify with the TASK BRIEF below. The spec lands in
   .specify/specs/<slug>/spec.md. Then STOP: report the spec path and its
   open questions — GATE 1 is the user's, relayed by the orchestrator.
2. After GATE 1 clearance, consult 'advisor' on open design decisions
   (herdr agent prompt advisor "..." --wait) and pressure-test locked
   decisions with 'skeptic' (herdr agent prompt skeptic "..." --wait).
3. Run /speckit-plan against the approved spec; 'reviewer' validates it
   via the plan checklist before it is considered final.
4. Run /speckit-tasks; 'reviewer' validates via the tasks checklist.
5. Nothing advances past a reviewer 'fixes-needed'. No superpowers
   specs/plans — new-work artifacts live under .specify/ only.

## seat: advisor
You are the DESIGN ADVISOR. Help the planner evaluate tradeoffs, component
interfaces, and decomposition. Find concrete solutions when the skeptic
identifies failure modes. Consultation only — never edit files.

## seat: skeptic
You are the SKEPTIC. Do not agree passively: probe edge cases, failure
modes, race conditions, breaking changes. Enforce repo constraints —
1000-line ceiling (scripts/check_file_size.py), cross-stage call ban,
clean Pydantic schemas, backwards compatibility. Demand mitigations for
every highlighted flaw. Never edit files.

## seat: reviewer
You are the SPEC & PLAN REVIEWER. Judge artifacts ONLY by the spec-kit
checklists in .specify/templates/checklists/ (spec cross-check, plan
checklist, tasks checklist): every requirement traceable, tasks
bite-sized, no placeholders, exact file paths, explicit test commands.
Reply exactly 'approve' or 'fixes-needed' with the checklist gaps named.
```

- [ ] **Step 4: Write exec briefs**

`.workspace/crew/v3/modes/exec/briefs.md`:

```markdown
## seat: executor
You are the IMPLEMENTER (spec-kit implement → converge) and the only seat
that writes to the repo.
1. Run /speckit-implement executing the tasks in the plan's tasks.md —
   never the spec instead of the tasks.
2. Per task, TDD is mandatory and test-first via the QA seats: dispatch
   'qa-happy' and 'qa-chaos' (herdr agent prompt <seat> "task N: ..." --wait)
   to write failing tests; verify RED yourself before writing code.
3. Reviewer gate is per-task and BLOCKING: you may not start task N+1
   until 'reviewer' has replied approve/fixes-needed on task N's diff and
   you addressed every fixes-needed.
4. Commit per task: git commit -F <msgfile>, one path per git add, no
   attribution trailers of any kind.
5. After the last task, run /speckit-converge. Loop implement→converge
   until it reports Converged — STOP-GUARD: at most 3 loops, then halt,
   diagnose, and wait for an orchestrator ruling.
6. After Converged, prompt 'scribe' to update living docs.

## seat: qa-happy
You are the CONTRACT & HAPPY-PATH QA. Given a task, write failing unit
and integration tests for valid inputs, expected behavior, and schemas.
Verify tests FAIL (RED) before signaling completion. Only test files in
tests/ — never production code.

## seat: qa-chaos
You are the CHAOS & EDGE-CASE QA. Given a task, write failing tests for
edge cases: None/empty values, network timeouts, invalid inputs, race
conditions, exception handling. Verify tests FAIL (RED) first. Only test
files in tests/ — never production code.

## seat: reviewer
You are the CODE REVIEWER & GATEKEEPER. Review every task diff before its
commit: repo constraints (1000-line ceiling via scripts/check_file_size.py,
mypy, ruff, no cross-stage calls), tests actually cover the task, no scope
creep beyond tasks.md. Reply exactly 'approve' or 'fixes-needed' — silence
is never approval.

## seat: scribe
You are the LIVING DOCUMENTATION SCRIBE. When implementation has converged,
update README.md / ARCHITECTURE.md / stage contracts touched by the change,
and any ADR or roadmap rows. Never push a file over the 1000-line ceiling.
Wait for the executor's call after convergence.
```

- [ ] **Step 5: Write bug briefs**

`.workspace/crew/v3/modes/bug/briefs.md`:

```markdown
## seat: bug-lead
You are the BUG LEAD (spec-kit assess → fix → test) and the only seat that
writes to the repo.
1. Run /speckit-bug-assess "<symptom from TASK BRIEF>" slug=<slug> — agree
   the slug with the orchestrator first. Then STOP at the CAUSE GATE: the
   assessed cause goes to the orchestrator/user before any fix.
2. After clearance, dispatch 'qa-happy' and 'qa-chaos' to write RED
   regression tests (the symptom must reproduce as a failing test); verify
   RED yourself.
3. Run /speckit-bug-fix — fix the assessed cause only, no drive-bys.
4. Run /speckit-bug-test. The final verdict must be 'verified';
   'partial' or 'failed' → stop, diagnose, wait for an orchestrator ruling.
   Missing verification is not a successful fix.
5. Artifacts stay in .specify/bugs/<slug>/. Commit rules as always:
   git commit -F, no attribution trailers.

## seat: qa-happy
You are the REGRESSION QA (happy path). Write the failing test that
reproduces the reported symptom on valid inputs, plus contract tests around
the fix surface. Verify RED first. Only test files in tests/.

## seat: qa-chaos
You are the REGRESSION QA (chaos). Write failing tests for edge cases
around the fix surface: boundary values, error paths, concurrency, stale
state. Verify RED first. Only test files in tests/.

## seat: reviewer
You are the BUG REVIEWER. Review the chain: diagnosis → regression tests →
diff. The fix must address the assessed cause and nothing else; tests must
fail without the fix. Reply exactly 'approve' or 'fixes-needed'.
```

- [ ] **Step 6: Write assess briefs**

`.workspace/crew/v3/modes/assess/briefs.md`:

```markdown
## seat: assessor
You are the IDEA ASSESSOR (spec-kit intake → research → define → shape →
decide). You write NOTHING outside .specify/assessments/<slug>/.
1. Agree the slug with the orchestrator, then run /speckit-assess-intake
   with the TASK BRIEF, followed by research, define, shape, decide —
   one skill at a time, artifacts under .specify/assessments/<slug>/.
2. Refine existing stage markdown rather than regenerating whole stages.
3. Consult 'advisor' on evidence gaps and criteria; put every draft
   decision past 'skeptic' for the kill-case before finalizing.
4. The decide artifact ends go / needs-clarification / kill and goes to
   the orchestrator for the USER GATE. A documented kill is a good result.

## seat: advisor
You are the ASSESSMENT ADVISOR. Help structure evidence, open questions,
and decision criteria; suggest the cheapest experiment per unknown.
Consultation only — never edit files.

## seat: skeptic
You are the ASSESSMENT SKEPTIC. Pressure-test for premature 'go': demand
disconfirming evidence, name the top failure scenarios, challenge every
assumption labeled as fact. Never edit files.
```

- [ ] **Step 7: Run tests to verify all modes pass**

```
& "C:\Program Files\Git\bin\bash.exe" .workspace/crew/v3/tests/run-tests.sh
```

Expected: `ok:` for fixture logic AND `ok: mode <m> validates` for constitution, plan, exec, bug, assess; final line `ALL PASS`.

---

### Task 4: entry scripts and popups

**Files:**
- Create: `.workspace/bin/herdr-v3-constitution`, `herdr-v3-plan`, `herdr-v3-exec`, `herdr-v3-bug`, `herdr-v3-assess`
- Create: `.workspace/bin/herdr-v3-plan-popup`, `herdr-v3-exec-popup`

**Interfaces:**
- Consumes: `crew_run <mode>` from Task 2 `_crew.sh`; modes from Task 3.
- Produces: CLI surface used by the orchestrator and Task 6 protocol text: `herdr-v3-<mode> ["<task brief>"] [--layout-only]`, env `SEAT_PREFIX=<x>` for parallel tabs.

- [ ] **Step 1: Write the five entry scripts**

Each entry is three functional lines; only `MODE=` differs. `.workspace/bin/herdr-v3-constitution`:

```bash
#!/usr/bin/env bash
# v3 crew entry: constitution tab (one-time). Usage: herdr-v3-constitution ["<seed note>"] [--layout-only]
set -euo pipefail
MODE=constitution
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/crew/v3/lib/_crew.sh" "$MODE" "$@"
```

`.workspace/bin/herdr-v3-plan` — same file with header comment `# v3 crew entry: SDD plan tab (specify/plan/tasks). Usage: herdr-v3-plan "<feature>" [--layout-only]` and `MODE=plan`.

`.workspace/bin/herdr-v3-exec` — `# v3 crew entry: SDD exec tab (implement/converge). Usage: herdr-v3-exec "<plan slug or tasks.md path>" [--layout-only]`, `MODE=exec`.

`.workspace/bin/herdr-v3-bug` — `# v3 crew entry: bug tab (assess/fix/test). Usage: herdr-v3-bug "<symptom>" [--layout-only]`, `MODE=bug`.

`.workspace/bin/herdr-v3-assess` — `# v3 crew entry: idea assessment tab. Usage: herdr-v3-assess "<idea>" [--layout-only]`, `MODE=assess`.

- [ ] **Step 2: Write the two popups**

`.workspace/bin/herdr-v3-plan-popup` (mirrors the v2 popup pattern — log, cd, run, pause):

```bash
#!/usr/bin/env bash
# Keybinding wrapper (prefix+alt+p): build the v3 SDD plan tab.
set -uo pipefail
LOG="D:/own/Kroker/.workspace/herdr-v3-plan-popup.log"
{
  cd "D:/own/Kroker" || { echo "cd failed"; exit 1; }
  date; pwd
  ./.workspace/bin/herdr-v3-plan "$@"
  echo "EXIT=$?"
} 2>&1 | tee "$LOG"
read -r -p "press enter to close"
```

`.workspace/bin/herdr-v3-exec-popup` — identical with `LOG="D:/own/Kroker/.workspace/herdr-v3-exec-popup.log"` and `./.workspace/bin/herdr-v3-exec "$@"`.

- [ ] **Step 3: Make all seven executable and syntax-check**

```
& "C:\Program Files\Git\bin\bash.exe" -c 'chmod +x .workspace/bin/herdr-v3-* .workspace/crew/v3/tests/run-tests.sh; for f in .workspace/bin/herdr-v3-* .workspace/crew/v3/lib/_crew.sh .workspace/crew/v3/tests/run-tests.sh .workspace/crew/v3/modes/*/layout.sh; do bash -n "$f" || echo "SYNTAX FAIL: $f"; done; echo SYNTAX-OK'
```

Expected: `SYNTAX-OK` with no FAIL lines.

- [ ] **Step 4: Fail-fast checks (no herdr needed)**

```
& "C:\Program Files\Git\bin\bash.exe" .workspace/bin/herdr-v3-plan --layout-only
```

Expected: exits non-zero with `_crew: no focused herdr workspace (is a herdr client attached?)` — proves mode loading, validation, and the workspace guard run before any herdr call. A mode-name typo test: `.workspace/bin/herdr-v3-bogus` (create a temp copy with `MODE=bogus`) must print `unknown mode 'bogus'`.

---

### Task 5: herdr keybindings repoint

**Files:**
- Modify: `C:\Users\start\AppData\Roaming\herdr\config.toml` (the two `[[keys.command]]` popup blocks for prefix+alt+p / prefix+alt+e)

**Interfaces:**
- Consumes: popups from Task 4.
- Produces: `prefix+alt+p` → v3 plan tab, `prefix+alt+e` → v3 exec tab. v2 scripts stay invocable manually.

- [ ] **Step 1: Edit the two command blocks**

In `config.toml`, replace the `prefix+alt+p` block's `command` and `description` lines:

```toml
command = "\"C:\\Program Files\\Git\\bin\\bash.exe\" \"D:/own/Kroker/.workspace/bin/herdr-v3-plan-popup\""
description = "kroker v3: build the SDD plan tab (specify/plan/tasks)"
```

and the `prefix+alt+e` block's:

```toml
command = "\"C:\\Program Files\\Git\\bin\\bash.exe\" \"D:/own/Kroker/.workspace/bin/herdr-v3-exec-popup\""
description = "kroker v3: build the SDD exec tab (implement/converge)"
```

- [ ] **Step 2: Verify config parses**

```
herdr status
```

Expected: exit 0, no config-parse errors (run inside an existing herdr session; herdr reloads config on key use — pressing prefix+alt+p in the TUI is the live check, done in Task 7).

---

### Task 6: protocol and guide rewrite

**Files:**
- Modify: `.workspace/orchestration-protocol.md` (replace the "Phase gates" section; add side entries)
- Modify: `.workspace/orchestration-guide.md` (seats table, run lifecycle, file map, quick start)

**Interfaces:**
- Consumes: entry names from Task 4 (`herdr-v3-constitution|plan|exec|bug|assess`), artifact roots from Task 1.
- Produces: the documented process the orchestrator and crew follow; all other protocol sections (role contract, topology, rulings, driving, integration, inbox, sizing) unchanged.

- [ ] **Step 1: Replace the protocol's phase-gates section**

Replace the entire `## Phase gates (superpowers sequence — never skip)` section with:

```markdown
## Phase gates (spec-kit SDD — never skip)

1. **Constitution (once per repo).** `herdr-v3-constitution`: planner
   drafts `.specify/constitution.md` via /speckit-constitution seeded
   from repo rules. **USER GATE** — constitution approval.
2. **Specify.** `herdr-v3-plan "<feature>"`: planner runs
   /speckit-specify; spec lands in `.specify/specs/<slug>/spec.md`.
3. **USER GATE** — spec approval plus rulings on its open questions.
4. **Plan + tasks.** /speckit-plan then /speckit-tasks; the reviewer
   seat validates each against `.specify/templates/checklists/` before
   the artifact is final. **USER GATE** — plan approval.
5. **Implement.** `herdr-v3-exec`: executor runs /speckit-implement
   against tasks.md — RED tests from the qa seats first, reviewer gate
   per task (blocking), commit per task.
6. **Converge.** /speckit-converge; loop implement→converge until
   `Converged`; stop-guard at 3 loops → halt, diagnose, orchestrator
   ruling. Scribe updates living docs after convergence.
7. Orchestrator verification (`herdr-verify`) → fast-forward `main` →
   push.

Side entries (independent, not phases of the above):

- **Bugs** from inbox triage → `herdr-v3-bug "<symptom>"`:
  /speckit-bug-assess → **cause gate** (orchestrator/user) → RED
  regression tests via qa seats → /speckit-bug-fix → /speckit-bug-test;
  only a `verified` verdict closes the bug.
- **Register ideas** → `herdr-v3-assess "<idea>"`:
  /speckit-assess-intake → research → define → shape → decide; the
  go / needs-clarification / kill decision is a **USER GATE**; artifacts
  in `.specify/assessments/<slug>/`.

Brief discipline, crew topology, standing rulings, driving-and-waiting,
integration, inbox, and sizing sections above carry over unchanged;
wherever they name docs/superpowers/specs|plans for NEW work, read
.specify/specs/<slug>/ instead (historical superpowers artifacts stay
where they are).
```

- [ ] **Step 2: Update the guide**

In `.workspace/orchestration-guide.md`:

1. Replace the seats table with:

```markdown
| Seat | Mode/tab | Model | Does |
|---|---|---|---|
| planner | constitution / plan | flagship (claude) | /speckit-constitution once; then /speckit-specify → plan → tasks |
| assessor | assess | flagship (claude) | /speckit-assess-* through the decide gate |
| bug-lead | bug | opencode | /speckit-bug-assess → fix → test (verified only) |
| executor | exec | opencode | /speckit-implement + /speckit-converge; the only repo-writing seat |
| qa-happy / qa-chaos | exec / bug | glm (shim) | RED tests first, every task; never production code |
| skeptic | plan / assess / constitution | agy | devil's advocate, failure modes, repo constraints |
| advisor | all plan-side tabs | flagship (claude) | tradeoffs, consensus — never edits files |
| reviewer | all | opencode / agy | spec-kit checklists (plan) · per-task diff gate (exec/bug) |
| scribe | exec | claude | living docs after convergence |
| orchestrator | main pane | you + me | briefs, rulings, verification, integration |
```

2. In "Run lifecycle", replace steps 2–6 wording so that: plan tab = `herdr-v3-plan` running /speckit-specify → GATE 1 → /speckit-plan + /speckit-tasks (reviewer per checklist) → GATE 2; exec tab = `herdr-v3-exec` running /speckit-implement with per-task reviewer gate, then /speckit-converge (≤3 loops). Add one sentence: "Bugs and register ideas have their own entries — `herdr-v3-bug` and `herdr-v3-assess`."

3. Replace the file-map rows for `.workspace/bin/herdr-plan | herdr-exec` with:

```markdown
| `.workspace/crew/v3/` | mode layouts + seat briefs (lib in `lib/`, modes in `modes/<mode>/`) |
| `.workspace/bin/herdr-v3-{constitution,plan,exec,bug,assess}` | v3 crew entry scripts |
| `.specify/` | spec-kit home: constitution, `specs/<slug>/`, `bugs/<slug>/`, `assessments/<slug>/`, checklists |
```

4. In "Quick start", replace the single-entry sentence with: "One message to the orchestrator: **'take <X> per the protocol'** (feature), **'fix <symptom>'** (bug), or **'assess <idea>'** — the crew routes to the right v3 entry; you stand at the gates."

- [ ] **Step 3: Verify the rewrite**

```
Select-String -Path .workspace\orchestration-protocol.md -Pattern 'speckit|herdr-v3' | Measure-Object -Line
Select-String -Path .workspace\orchestration-protocol.md -Pattern 'superpowers sequence'
Select-String -Path .workspace\orchestration-guide.md -Pattern 'herdr-v3|\.specify' | Measure-Object -Line
```

Expected: protocol has ≥8 speckit/herdr-v3 lines; the old `superpowers sequence` header is gone (no output); guide has ≥6 v3/.specify mentions.

---

### Task 7: live smoke in herdr and final acceptance

**Files:**
- No new files. Verifies Tasks 1–6 against a live herdr session.

**Interfaces:**
- Consumes: everything above.
- Produces: verified v3 setup; the constitution run itself is the first crew use (outside this plan).

- [ ] **Step 1: Layout-only smoke for every mode**

From a pane inside a herdr session (`$env:HERDR_ENV -eq 1`; if executing outside herdr, STOP and hand this step to the user — it cannot be simulated):

```
& "C:\Program Files\Git\bin\bash.exe" .workspace/bin/herdr-v3-plan --layout-only
& "C:\Program Files\Git\bin\bash.exe" .workspace/bin/herdr-v3-exec --layout-only
& "C:\Program Files\Git\bin\bash.exe" .workspace/bin/herdr-v3-bug --layout-only
& "C:\Program Files\Git\bin\bash.exe" .workspace/bin/herdr-v3-assess --layout-only
```

Expected per run: line `v3 <mode> tab ready: tab=w#:t# <seat>=w#:p# ...` matching the mode's declared seats; `herdr agent list` shows the started seats; qa seats in exec/bug run on the GLM endpoint (shim took effect). After each check, close the tab you created: `herdr tab close <tab_id>`.

- [ ] **Step 2: Keybinding check**

Press `prefix+alt+p` in the herdr TUI. Expected: popup runs `herdr-v3-plan-popup`, log tail at `.workspace/herdr-v3-plan-popup.log` shows the ready line; close the created tab. (If the key does nothing, `herdr status` and re-check Task 5 edits.)

- [ ] **Step 3: Scaffold acceptance recap**

Confirm in one pass: `specify --version` → 0.11.3; `.specify/` committed (Task 1 commit exists: `git log --oneline -1 -- .specify`); speckit skills visible to a claude seat (open the planner pane from Step 1 and run `/speckit-specify --help`-style discovery, or verify files exist under the paths staged in Task 1); tests green:

```
& "C:\Program Files\Git\bin\bash.exe" .workspace/crew/v3/tests/run-tests.sh
```

Expected: `ALL PASS`.

- [ ] **Step 4: Report**

Report to the user: scaffold commit hash, seven created files + ten mode files, keybinding state, smoke results per mode, and the recommended first real action — a live `herdr-v3-constitution` run.
