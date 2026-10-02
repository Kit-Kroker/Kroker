# Contract: zai route and base-URL policy

Home: `src/sdlc/agents/model_ids.py`. Extends `.specify/specs/004-model-forwarding-single-retry/contracts/model-resolution-contract.md`; nothing there is weakened.

## Environment

| Variable | Required | Meaning |
|---|---|---|
| `ZAI_API_KEY` | yes, when any proposer role is in the `zai` family | credential; read by the provider itself |
| `ZAI_BASE_URL` | no | overrides the endpoint; unset, empty or whitespace = default |

Default endpoint: `https://api.z.ai/api/coding/paas/v4`.

## Behaviour

- **C1.** For provider name `zai`, the provider returned to the framework has its client pointed at `ZAI_BASE_URL` if set and non-blank, otherwise at the default endpoint. For every other provider name the provider is exactly what the framework builds.
- **C2.** The environment is read when the provider is built, not at module import. A change of `ZAI_BASE_URL` takes effect for providers built after it.
- **C3.** `single_retry_layer()`: C1, plus SDK retry count 0 when the client exposes an integer `max_retries` (004 contract, unchanged).
- **C4.** `resolve_model(model_id)` / `route_layer()`: C1 only. SDK retry count is left at its default.
- **C5.** No HTTP client is constructed by this module. Credentials, timeouts and headers remain the SDK's defaults. A missing `ZAI_API_KEY` raises the provider's own error.
- **C6.** No fallback between endpoints. An endpoint error (authentication, balance) propagates as the provider's error.
- **C7.** Every site in `src/sdlc` or `agents/` that turns a model string into a model does so through `single_retry_layer()`, `route_layer()` or `resolve_model()`. The site list is plan.md D2; a guard test enforces it.
- **C8.** `validate_proposer_model` and `forwarded_model` are unchanged.

## Observable evidence

- Request path on a stub server begins with the configured base path and ends `/chat/completions`, for each site category, default and overridden.
- Under an always-failing stub, a durable proposer agent makes exactly its engine attempt budget of HTTP calls.
- Doctor: `zai` family present + key absent → fail naming `ZAI_API_KEY`; placeholder → fail naming the placeholder; set → pass.
