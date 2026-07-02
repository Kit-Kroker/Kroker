# ai-sdlc-temporal

Idea → deployed feature pipeline. Temporal orchestrates; Pydantic AI agents
think (clarify, architect, plan, QA, quality gate, devops); coding harnesses
do (`claude -p`, `opencode run`) inside isolated git worktrees.

## Roles
| Role | Kind | Runs as |
|---|---|---|
| clarify | Pydantic AI (TemporalAgent) | activity via TemporalAgent |
| architect | Pydantic AI | activity via TemporalAgent |
| planner | Pydantic AI | activity via TemporalAgent |
| dev / test / devops executor | coding harness | long-running heartbeating activity in a git worktree |
| qa analyst | Pydantic AI + test-suite activity | activities |
| quality gate | Pydantic AI (soft-gate policy) | activity via TemporalAgent |
| reviewer | coding harness (different model/harness than dev) | activity |

## Human-in-the-loop
Gates: clarify, architecture, plan, merge, deploy — each `hard` / `soft` /
`off` per project (`PipelineConfig.gates`). Humans interact through signals:

```
python -m sdlc.cli start --title "Add SSO" --mode brownfield --repo git@...
python -m sdlc.cli status  --id feature-add-sso
python -m sdlc.cli answer  --id feature-add-sso --q Q1 --text "Use OIDC"
python -m sdlc.cli approve --id feature-add-sso --gate architecture
```

## Run
1. `temporal server start-dev`
2. `pip install -e .` then `python -m sdlc.worker`
3. `python -m sdlc.cli start ...`

## Notes
- Payloads through Temporal stay small (claim-check for specs/diffs/logs).
- Agent names / toolset ids are activity names — never rename in prod.
- Harness sessions are resumed across fix-loop attempts (claude `--resume`,
  opencode `-s`), so the fixer keeps its context.
- Cross-harness review: configure `roles["reviewer"]` with a different
  harness/model family than `roles["dev"]`.
