# Team console (`E-93`…`E-109`) → FR-1500, P7

**Source.** The v13 console design (Pipeline Canvas v13, exported under
`docs/reference/Pipeline management prototype-project/`) and its
screen-by-screen spec, [`docs/reference/kroker-ui-spec-v13.md`](../reference/kroker-ui-spec-v13.md).
The spec's section numbers are cited as *spec §n* below. Requirements:
PRD FR-1500 (v1.3, 2026-11-22). Storage decision: ADR-26.

**What P7 is.** FR-601 gave one operator a dashboard over runs. P7 turns it
into a console a team in one company works in: projects with people and
roles, decisions that reach the role owning them, a chat thread per task in
which Kroker proposes and a person confirms, and draft → measure → publish
for every change to how work gets done. One company, self-hosted. Tenancy,
self-serve onboarding, minted per-run credentials and the model proxy stay
in P8 ([`service-platform.md`](service-platform.md)).

**Exit criterion (PRD §9).** In one project with at least three people in
distinct roles: a work item started from chat reaches merge with every
decision routed by role and recorded with a real principal; one pipeline or
agent change goes draft → measure → publish; one automation from an
external trigger goes shadow → live.

**What it starts from.** The v5 console (FR-601, round 018) already has the
`@kroker/ui` library (FR-1400), Fleet, Inbox, the run page (Graph and Board
tabs), Graphs catalog + Design editor, Compare and Interfaces, served by the
FastAPI backend in `src/sdlc/dashboard/` (17 routes over Temporal). The MCP
server has twelve verbs over stdio (E-11), the operator chat surface exists
(E-86, `interfaces/chat/`), and the prompt gate exists (E-82,
`src/sdlc/eval/gate.py`). Every v13 screen marked **Exists** in the spec maps
onto one of these; P7 adds the parts marked Partial, Planned and New.

---

## C0 — Foundations (nothing else in P7 can start without these)

- [ ] **E-93 — Control-plane store, projects, membership** → FR-1501,
  ADR-26; spec §0, §1.1, §13.1. A `control_plane/` service in `src/sdlc/`
  over Postgres: company, projects (name, goal, colour, bound repos and
  tools), members with a role per project. Every row carries `company_id`.
  A run records its `project_id` at start (workflow input plus a Temporal
  search attribute), so every list filters by project without a join
  against the store. *Gap:* everything; today the only project notion is
  the `project:<repo>` memory bank and the board's identity. *Decide in the
  spec:* how existing runs without a project render (a "No project" bucket,
  not a migration).
- [ ] **E-94 — Principals and roles inside one company** → FR-1004 (company
  half; split from E-60, which keeps SSO, per-tenant roles and remote MCP
  auth for P8); spec §3 routing, §13.1. Authenticated users on the dashboard
  API and the chat; every `GateDecision` records a real principal instead of
  today's self-asserted `decided_by` (`src/sdlc/dashboard/api.py:14` names
  this as the point where that stops being acceptable). Roles: Owner, Tech
  lead, Product owner, Developer, Designer, QA, Marketing, Viewer (spec §13.1
  also lists Lead and Platform engineer; settle the list in the spec).
- [ ] **E-95 — Console shell v13** → FR-1501; spec §1. Sidebar (project
  switcher, Inbox and Work counters, navigation, chat list grouped Pinned /
  Today / Earlier with the "you" badge), command palette, toasts that say
  what changed and for whom, settings frame, theme. New components follow
  FR-1400…FR-1406 (clause contract, profile, Playwright); the prototype's
  `tokens/tokens.css` is reconciled into `interfaces/ui/src/tokens/` rather
  than copied. Replaces the v5 header navigation; v5 screens keep working
  inside the new shell until their own epic restyles them.

## C1 — The daily loop (decisions, work, chat, read surfaces)

- [ ] **E-96 — Decisions routed to roles, in plain language** → FR-1502,
  FR-1503; spec §3, §13.1 "Who decides". *Builds on:* `pending.py`,
  `workflows/gates.py`, the Inbox feature, `policy/notifications.yaml`. The
  "Who decides" table lives per project in the store; the workflow still
  owns the decision, and the first signal wins as today. Adds the
  plain-language fields (lead, facts, outcome per button, technical
  details), the "For me" / "My projects" tabs, the tool-escalation counter
  ("1 of 3", `max_tool_escalations`), the budget decision ("Add $10" /
  "Stop"), and deny-on-timeout for tool escalations. *Gap:* role routing and
  the plain-language fields are new; the decision kinds all exist.
- [ ] **E-97 — Work items with provenance; Home, Work, New work item** →
  FR-1505; spec §2.1, §4. *Builds on:* `/fleet/summary`, `run_summary()`,
  `POST /runs`. Adds source and external ref, project, waiting-on; filters
  (All · Needs you · In progress · Closed); Board by phase and Table; Home's
  "Waiting on you" and "In progress"; the New work item form, whose "How to
  run it" maps onto triage / `default` / `default-research` / `seeded` and
  whose gate tiles read the pipeline's gate config.
- [ ] **E-98 — Chat threads and Kroker's action set** → FR-1504; spec §2.2.
  *Builds on:* the E-86 chat agent and the operator verbs in
  `sdlc/operator/tools.py` (the same verbs the MCP server exposes), so a
  chat card and an MCP call change state through one code path. Thread
  model in the store (messages, system events, cards, participants,
  visibility, pin); cards Queue work, Create graph, Save version, Answer
  decision, Apply proposal, Navigate; nothing changes state before the
  confirm click. Decision cards are references rendered from the workflow
  (ADR-26). Chat dock (⌘J). The prototype's fixed phrases are Demo; the
  target is the LLM with the typed action set.
- [ ] **E-99 — Cross-run read surfaces: artifacts, memory, metrics** →
  FR-1515; spec §6, §12. Artifacts listed by project and kind from the
  claim-check store (`artifacts/store.py`). Memory read API by bank and kind
  with the per-run recall snapshot link (`<run_id>/recall/<hash>.json`); the
  prototype's memory screen is replaced by the target in spec §6.2, and
  "Used n×" becomes "recalled by n runs" or is dropped. **Blocked on OQ-11**
  (bank per project or per repository). Metrics per project and source, plus
  decision wait time (opened → decided), from run outcomes and E-33's role
  costs; edit/forget for memory items stays out (FR-1007, P8).

## C2 — Run depth (not on the exit path)

- [ ] **E-100 — Live session and steer** → FR-1506; spec §5.1. Stream
  `HarnessSession` events (ADR-16) to the run view; steer text delivered as
  a user turn at the next tool boundary and queued while a tool escalation
  pauses the session; "Model on this node · configured / answered" with the
  defect note when they differ (`dashboard/run_graph.py`).
- [ ] **E-101 — Pull to local, push back** → FR-1506; spec §2.2, §5.1.
  `pull_task` / `push_task` MCP verbs: the run waits under a lock with an
  expiry, the task branch is handed to the person's machine, push back runs
  the task's frozen tests, then review and QA. Release returns the task to
  the agent.

## C3 — Factory: how work gets done

- [ ] **E-102 — Pipeline draft → measure → publish; simple view** →
  FR-1507; spec §7, §5.4. *Builds on:* `graph/store.py`, `graph/validate.py`,
  `graph/node_types.py` (`canonical_stage`), the Design editor and the
  benchmark. A draft holds unpublished changes; Measure runs the draft
  against the live version on benchmark cases and reports through an Inbox
  decision; Publish makes a new `content_sha` live for new runs; Definition
  history with "Make live". Simple view: phases from `canonical_stage`, gates
  as badges, gate policy edits, the remove-step rules of spec §7.5. *Gap:*
  draft, measure job, "live" pointer per pipeline, simple-view mapping.
- [ ] **E-103 — Layered agent configuration; agent page** → FR-1509; spec
  §8. *Builds on:* `agents/loader.py`, `agents/registry.yaml`, `RoleConfig`.
  Company → project → agent resolution with the source of each value and
  reset; the effective `agent.yaml`; checks before publishing (ADR-6 family,
  thin prompt, no eval cases, harness limits, no budget); agent versions
  under the same draft → measure → publish as E-102. *Decide in the spec:*
  where project overrides live — they must be content-addressed so a run
  pins them (ADR-5), which argues for override files hashed into the run
  config rather than mutable rows. Fields marked *planned* in spec §8.3
  (advisor, sub-agents, notebook, tool-call judge) stay out of P7.
- [ ] **E-104 — Shadow mode and the `agent.custom` node** → FR-1508; spec
  §7.3–7.5, §10.2. A generic node type whose output is one of three typed
  models (check report, document, code change); config-only roles; shadow
  execution records verdicts and never routes, blocks, opens a decision or
  posts externally; Go live is a draft change. The NG8 boundary: a custom
  step adds a typed node, never an untyped one.
- [ ] **E-105 — Proposals measured before applied** → FR-1513; spec §3
  Proposals. *Builds on:* the retro stage (E-32) and the prompt gate (E-82).
  A measurement job per proposal (one change per measurement), verdicts
  (helped / hurt / no observed effect / confounded), Apply as a new version
  through the prompt gate.
- [ ] **E-106 — Harness catalogue and install** → FR-1511; spec §9. *Builds
  on:* `harness/base.py`, the three CLI adapters, `harness/registry.py`'s
  drift check (E-24), `crew/`. Installed harnesses with their control
  matrix; a registry of known coding agents (candidate source: the ACP
  registry); install = adapter + one verified benchmark case; strict
  containment refuses a harness that enforces nothing. The SDK harness stays
  Planned. Supersedes the Interfaces screen in the main flow.
- [ ] **E-107 — Agent builder and dry-run** → FR-1510; spec §10. An LLM
  agent with tools that write the same draft fields as the forms, in step,
  agent and automation modes; Test tab replays the draft read-only on the
  stored inputs of recent runs. Depends on E-103 (fields), E-104 (where a
  step lands), E-109 (automation mode).

## C4 — Reach: connections and automations

- [ ] **E-108 — Connections, bindings, agent access; model routing** →
  FR-1514; spec §13.1–13.2. Integrations connected by owners and bound per
  project by leads, every change an audited policy diff; the agent-access
  matrix (role × tool) enforced through containment (FR-703); Models and
  keys shows sources and per-project routing with the ADR-6 check.
  Credentials stay worker environment variables in P7: minted per-run
  tokens are E-59 and the vault and model proxy are P8.
- [ ] **E-109 — Automations and issue triggers** → FR-1512; spec §11.
  *Builds on:* `schedules/`, `ReflectWorkflow`, the triage workflow host,
  `cli_roles.py`. Every automation has a trigger, an action, a run-as
  identity and a budget owner, and starts in shadow (E-104). Linear, GitHub,
  Slack and Sentry triggers enter through the planned `intake.issue` node.
  Templates and "From Kroker" managed automations (triage, retro digest,
  nightly reflect) are views over what already runs.

---

## Ordering inside P7

1. **C0 first, in order E-93 → E-94 → E-95.** Every other epic needs a
   project on the run and a principal on the decision.
2. **C1 next: E-96 and E-97 in parallel, then E-98.** The chat's cards call
   the verbs E-96/E-97 make project-aware. E-99 can go any time after E-93,
   except its memory half, which waits on OQ-11.
3. **C3 in the order E-102 → E-104 → E-103 → E-105 → E-106 → E-107.** The
   draft/measure/publish machinery is shared, so pipelines prove it first;
   the builder comes last because it only writes fields the forms already
   have.
4. **C4: E-108, then E-109.** Automations need bound integrations and
   shadow mode.
5. **C2 is off the exit path** and can run beside C3.

The exit path is E-93, E-94, E-95, E-96, E-97, E-98, E-102, E-104, E-108,
E-109; the other seven are inside P7 but do not gate its exit.

## What moves between phases

- **E-60 splits.** Principals and roles inside one company are E-94 (P7).
  SSO, per-tenant roles and authenticated remote MCP stay E-60 (P8).
- **E-59 stays P8.** P7 enforces the access matrix through containment with
  environment credentials; minted per-run, repo-scoped tokens are E-59.
- **Key vault and model proxy have no epic yet.** The spec's "Planned: today
  keys are worker environment variables" needs one in P8; the closest fit is
  E-62 (configurable model provider).
- **P6's remaining audit depth (E-52…E-56) is scheduled after P7** (owner
  decision, 2026-11-22). It does not block P7 and P7 does not block it.

## Reconciliation notes against the spec

Checked against the repository on 2026-11-22; the spec is a design source
and these are the places it disagrees with the tree.

- **Epic numbers in spec §13.2/§15.** "vault (E-59)" and "metering (E-60)"
  do not match: E-59 is repository connection (FR-1003), E-60 identity
  (FR-1004), E-61 metering (FR-1005). No epic owns a vault (see above).
- **Prompt gate.** The spec's E-82 is shipped (`src/sdlc/eval/gate.py`,
  plan `docs/superpowers/plans/2026-08-11-promptfoo-prompt-gate.md`) but has
  no row in the roadmap's epic files.
- **Memory screen** (spec §6.2) is marked by the spec itself as needing
  change; E-99 builds the target behaviour, not the prototype.
- **Interfaces screen** (spec §5.4) is superseded by Factory → Harnesses
  (E-106) and is kept only as a secondary view.
- **Every count, cost and percentage in the prototype is synthetic** unless
  the spec's §15 says the data exists.
