# Contract — the MCP surface an operator's client sees

Server: `kroker-mcp` (binary from `interfaces/mcp/`), stdio, rmcp ~3.10.
Advertised capabilities: `tools` only (no resources, prompts, sampling or
logging).

## Verb mapping (FR-602 → tool → Python verb → seam path)

| FR-602 | MCP tool | `tools.py` verb | read_only | confirm | Result shape |
|---|---|---|---|---|---|
| list | `list_runs` | `list_runs(status="open")` | yes | none | text (`render.runs_view`) |
| detail | `get_run` | `get_run(run_id)` | yes | none | text |
| inbox | `inbox` | `inbox()` | yes | none | text |
| answer | `answer_question` | `answer_question(run_id, key, text)` | no | pending | structured `ReplyReceipt` |
| decide | `decide_gate` | `decide_gate(run_id, key, outcome, text="")` | no | pending | structured `ReplyReceipt` |
| start | `start_run` | `start_run(title, mode, description="", repo=None)` | no | start | text (run id) |
| — | `follow` | `follow(run_id=None, timeout_s=60)` | yes | none (progress) | structured `ChangeReport` |
| — | `list_projects` | `list_projects()` | yes | none | text |
| — | `get_project` | `get_project(project)` | yes | none | text |
| — | `list_tasks` | `list_tasks(project, plan_version=None, status=None)` | yes | none | text |
| — | `project_events` | `project_events(project, since=0)` | yes | none | text |
| — | `read_artifact` | `read_artifact(project, key, version_id=None, offset=0)` | yes | none | structured `ArtifactRead` (32 KB page) |

Every row reaches Python through the bridge `call` op
(contracts/bridge-protocol.md). No row has Rust-side logic. Names,
descriptions and schemas come from `describe`.

## Result rules

- Success with a text verb: one `text` content block, byte-identical to the
  verb's return value.
- Success with a typed verb: `structuredContent` = `Model.model_dump(mode="json")`,
  plus one `text` block with the same JSON; `outputSchema` advertised in
  `tools/list`.
- `ToolError`: `isError: true`, one `text` block = `ToolError.message`
  verbatim.
- `ReplyReceipt.confirmed=false`: `isError: false` (FR-006).

## Write confirmation (FR-005, research R4)

- **E1** (< 2026-07-28): `elicitation/create`, form mode, message =
  `PreviewResult.message`, requestedSchema
  `{type: object, properties: {confirm: {type: boolean, title: "Confirm"}}, required: ["confirm"]}`,
  300 s timeout.
- **E2** (≥ 2026-07-28): `InputRequiredResult` with input request key
  `"confirm"` (the same form) and a sealed `requestState` (data-model.md
  SealedState).
- **Refusals** are `isError: true`. Each response below is listed with its
  text:
  - **No elicitation path in this session:** "this write needs a human
    confirmation that this MCP client did not provide; nothing was changed.
    Use the dashboard or `python -m sdlc.cli` instead."
  - **Decline, cancel, timeout or `confirm=false`:** "the operator did not
    confirm; nothing was changed"
  - **Bad, expired, replayed or mismatched state:** "this confirmation is
    invalid or was already used; nothing was changed — call the tool again"
  - **Digest mismatch:** the bridge `changed` sentence.

## Actor

`mcp:<normalised clientInfo.name>` (fallback `mcp:local`; override
`SDLC_MCP_ACTOR`, which must match `^mcp:[a-z0-9-]{1,40}$`). It is written
to `GateDecision.reviewer` only.

## Launch (client config)

```json
{ "mcpServers": { "kroker": {
    "command": "<repo>/interfaces/mcp/target/release/kroker-mcp",
    "args": ["--repo", "<repo>"] } } }
```

Options:
- `--repo <path>`: required; env fallback `SDLC_REPO_ROOT`.
- `--bridge-cmd <argv…>`: test override.
- `SDLC_MCP_PYTHON`: interpreter override.
- `SDLC_MCP_ACTOR`: actor override.
- The usual `TEMPORAL_HOST`, read by the bridge.
