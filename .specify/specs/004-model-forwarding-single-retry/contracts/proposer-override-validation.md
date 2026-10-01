# Contract: proposer override validation

## `validate_proposer_model(role, value) -> None`

Raises `RegistryError` naming the role, the string and the accepted form `provider:model`. Offline: no network, no credentials, no provider instantiation.

| Input | Result |
|---|---|
| `anthropic:glm-5.2`, `anthropic:claude-sonnet-4-6`, `openai:gpt-5.2`, `google:gemini-3.5-flash` | accepted (provider known and installed) |
| `openai/gpt-5.2`, `zai-coding-plan/glm-5.2`, `glm-5.2` | rejected: no provider part |
| `anthropic:`, `:glm-5.2` | rejected: empty part |
| `test` | rejected |
| `nosuch:model` | rejected: unknown provider |
| provider whose SDK extra is not installed | rejected |

The model name is not checked against any list (Q2).

## Where it runs

| Entry path | Call site | When |
|---|---|---|
| CLI `--role-model` | `cli_roles.build_role_overrides`, proposer branch | before the workflow is started |
| Benchmark arm | `benchmarks/matrix.py` at arm resolution; `benchmarks/workflow._cell_config` as backstop | at matrix expansion, before any cell runs |
| Graph node role | `graph/validate.py`, new problem beside the ADR-6 check | at graph validation |

Harness roles (`dev`, `test`, `devops`) are never passed to this check; their grammar and behaviour are unchanged. An arm `default` fans out to harness and proposer roles; only the proposer subset is validated.

## CLI-visible behaviour

`sdlc run ... --role-model architect=openai/gpt-5.2` exits non-zero before any workflow starts, with a message containing `architect`, `openai/gpt-5.2` and `provider:model`.
