# Data Model: Native zai Provider (005)

No persisted schema changes. No pydantic model gains or loses a field.

## Values that change

| Thing | Before | After |
|---|---|---|
| Registry `model` for analyst, architect, clarify, deep_review, devops_planner, handoff, merge_verdict, planner, qa, research, reviewer | `anthropic:glm-5.2` | `zai:glm-5.3` |
| Provider family of those roles (`model_family`) | `anthropic` | `zai` |
| Model id of those roles (`model_id`) | `glm-5.2` | `glm-5.3` |
| `RoleUsage.model`, `PriceUsageInput.model`, memo-key model component for those roles | old string | new string (one-time memo miss) |
| Price row used | `zhipuai` (unhinted fallback) | `zai` (hinted hit) |
| `wire_no_override.json` `model_id` entries (6) | old string | new string |

## Values that do not change

- Harness roles dev/test/devops: `zai-coding-plan/glm-5.2`.
- adversary `anthropic:claude-sonnet-4-6`; discover, risk `anthropic:claude-sonnet-4-5`.
- Activity names, attempt budgets, backoff, timeouts.
- ADR-6 outcomes: dev family `zai-coding-plan` ≠ reviewer family `zai`; adversary model id differs from dev (`glm-5.2`) and reviewer (`glm-5.3`).

## New configuration

| Name | Kind | Default | Read by |
|---|---|---|---|
| `ZAI_API_KEY` | env, required | — | provider (framework) |
| `ZAI_BASE_URL` | env, optional | `https://api.z.ai/api/coding/paas/v4` | `model_ids.zai_base_url()` |

## Doctor mapping

`provider family → key`: adds `zai → ZAI_API_KEY`.
