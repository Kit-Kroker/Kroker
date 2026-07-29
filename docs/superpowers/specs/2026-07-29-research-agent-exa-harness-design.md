# Research Agent: Exa & Harness Upgrade Design

## Purpose
Upgrade the existing `research` agent to leverage `ExaSearch` for deeper retrieval and `pydantic-ai-harness` capabilities (`CodeMode`, `TodoCapability`, `ConsoleCapability`, `ContextManagerCapability`) for robust orchestration, replacing the custom manual tools (`web_search` and `fetch_page`).

## Architecture & Components
1. **Capabilities Injection**:
   The `build()` function in `agents/research/agent.py` will be updated to inject harness capabilities:
   - `CodeMode`
   - `TodoCapability`
   - `ConsoleCapability`
   - `ContextManagerCapability(max_tokens=180_000)`
   - `ExaSearch(include_deep_search=True)`

2. **Tool Replacement**:
   - `agents/research/tools/web_search.py` and `agents/research/tools/fetch_page.py` will be deleted.
   - `read_repo.py` and `recall_leads.py` will remain as standard tools.

3. **Grounding Verification Interceptor**:
   - We will subclass or wrap `ExaSearch` (e.g., in `agents/research/exa_wrapper.py`).
   - The wrapped `get_page` tool will execute the original Exa API call and then persist the fetched page content to `$SDLC_RUNS_ROOT/<run_id>/research/pages/<sha256(url)>.txt`.
   - This ensures the existing strict `verify_brief_activity` pipeline step remains unmodified and continues to verify character-for-character grounding correctly.

4. **Prompt Updates**:
   - `instructions.md` will be updated to instruct the model to use `run_code` to orchestrate research, branch logic, and aggregate results using `asyncio.gather`.

## Testing & Integration
1. **The Temporal/TestModel Issue**:
   The rollback of `CodeMode` documented in `agent.py` was caused by `TestModel` serialization and execution issues within `TemporalAgent`. 
2. **Provider-Aware Capability Loading**:
   - `agent.py`'s `build` function receives a `provider` argument.
   - When `provider == "fake"` (which is the case in `test_research_e2e.py` due to `agent.yaml`), we will omit `CodeMode` and other complex harness capabilities to avoid serialization and test environment crashes.
   - This keeps the testing deterministic and bypasses the `TemporalAgent` + `CodeMode` impedance mismatch.

## Success Criteria
- The research agent successfully runs using `CodeMode` and `ExaSearch` in a live environment.
- Grounding verification passes for verbatim quotes from Exa-fetched pages.
- `test_research_e2e.py` continues to pass in the test suite without modifications to the `TestModel` fake.
