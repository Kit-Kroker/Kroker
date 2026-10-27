# Quickstart: validating round 019

All paths are absolute on the host. `WT` = `D:\own\Kroker-019glm52retire`.
Run the commands from Git Bash with `MSYS_NO_PATHCONV=1`.

## §1 The throwaway container (research D-5)

```bash
export MSYS_NO_PATHCONV=1
HEAD8=$(git -C /d/own/Kroker-019glm52retire rev-parse --short=8 HEAD)
docker run --rm -it --network kroker_default \
  -v D:/own/Kroker-019glm52retire:/app \
  -v kroker-verify-venv:/app/.venv \
  -v D:/own/Kroker/runs:/app/runs:ro \
  -v D:/own/Kroker/.env:/app/.env:ro \
  -v D:/own/sdlc-private-cases/cases:/srv/private-cases \
  -e SDLC_PRIVATE_CASES_ROOT=/srv/private-cases \
  -e KROKER_COMMIT=$HEAD8 \
  -w /app kroker-dev:latest bash
```

- Inside the container, never run `uv sync`. Use `uv run --no-sync …` or
  `/app/.venv/bin/python -m …`.
- `HEAD8` must be re-read after each commit that precedes a re-label.
- **Do not** start, stop or recreate `kroker-kroker-dev-1` or the compose
  worker (SG-7).

## §2 Pre-flight (Step 0)

1. **Catalog** (SG-6). On the worker, read only:

   ```bash
   docker exec kroker-worker-1 sh -c 'python3 -c "import json;d=json.load(open(\"/root/.cache/opencode/models.json\"));[print(k,v.get(\"status\")) for k,v in sorted(d[\"zai-coding-plan\"][\"models\"].items())]"'
   ```

   Expected: `glm-5.3 None` and `glm-5.3-flash None`.
2. **Manifest** (D-9). On the host, from `D:\own\Kroker\runs\benchmarks`:
   one line per file, `<sha256>  <forward-slash relative path>`, sorted by
   path, written to `WT\.specify\specs\019-glm52-arm-retirement\baseline-records.sha256`.
   Use the 017 recipe (`tasks.md` T-step "Write baseline-records.sha256").
3. **Baseline** (`baseline.md`):
   - `git show HEAD:<case>/acceptance.yaml` for the seven repo cases;
   - `git -C D:/own/sdlc-private-cases show HEAD:cases/theatre-box-office/acceptance.yaml`;
   - `uv run --no-sync python -m sdlc.cli benchmark corpus` (container);
   - `uv run --no-sync pytest` (fast tier) failures list;
   - `uv run --no-sync pytest -m temporal tests/replay` result.

## §3 FR-009 RED → GREEN (Step 1)

```bash
uv run --no-sync pytest tests/test_benchmark_corpus.py -k arm_drift   # RED: exactly T1–T4 fail
# ... implement data-model §3 ...
uv run --no-sync pytest tests/test_benchmark_corpus.py                # GREEN
```

## §4 Re-label loop (Steps 4–5)

Per case, after its `case.yaml` edit:

```bash
uv run --no-sync python -m sdlc.cli benchmark accept --case <case_id>
```

- Compare the printed line with contract §2.
- Then check the file:
  - `separation.strong.arm == zai-coding-plan-glm-5.3`;
  - `separation.strong.run_ids == []`;
  - `reference.detail` and `floor.detail` do not start with
    `oracle environment failed`;
  - both `tests_total` values are greater than 0.
- On any miss, `git checkout -- benchmarks/cases/<id>/acceptance.yaml` (or
  the `PRIV` equivalent) and stop.

After all cases:

```bash
uv run --no-sync python -m sdlc.cli benchmark corpus     # contract §3: 0 of 8, no stale row
```

## §5 Close (Step 7)

1. **Manifest re-check**: recompute and `diff` against
   `baseline-records.sha256`. The output must be empty (SG-1).
2. **SC-001 sweep**: on the host, from `WT`.

   ```bash
   git grep -n "glm-5\.2" -- benchmarks/cases agents benchmarks/config.yaml src/sdlc/core/models.py src/sdlc/benchmarks/importers/deveval.py
   grep -rn "glm-5\.2" /d/own/sdlc-private-cases/cases/*/case.yaml
   ```

   **Pass condition**: no live **YAML** text names glm-5.2, meaning no
   occurrence outside a `#` comment. That covers every `model:`, `name:`,
   arm, role-model, `models:` item and `extra_args_by_model` key. Check it
   mechanically:

   ```bash
   grep -nE "^[^#]*glm-5\.2" benchmarks/cases/*/case.yaml agents/*/agent.yaml benchmarks/config.yaml /d/own/sdlc-private-cases/cases/*/case.yaml
   ```

   It must print nothing. At base `6ba483a6` it prints 51 lines, 7 of them
   in cat-cafe. That count proves the command detects every declaration
   form: `weak_arm`, the arm `name`, dev/test/devops, the `models` item and
   the `extra_args_by_model` key. In the Python files, the shipped
   strings must be gone: `git grep -n '"zai-coding-plan/glm-5.2"' --
   src/sdlc/core/models.py src/sdlc/benchmarks/importers/deveval.py` may
   print only `src/sdlc/core/models.py:190`, which is a `# e.g.` field
   comment.

   **Allowed hits in the broad sweep** (history and out-of-scope comments,
   not declarations): the FR-006 comment blocks; the todo-api
   (`case.yaml:31–34`) and crew-probe (`case.yaml:34`) comments; the
   `benchmarks/config.yaml` comment, if any history remains in it;
   `agents/planner/agent.py:26` (a Python comment on the
   `anthropic:glm-5.2` rollback route); and `src/sdlc/core/models.py:190`
   (a `# e.g.` field comment). Any other hit fails SC-001.
2a. **FR-010 docs**: `git grep -n "dev=zai-coding-plan/glm-5\.2" -- README.md`
   prints nothing. `grep -n "R019" BENCHMARK.md` shows the break marker,
   whose per-case table has 8 rows. `python scripts/check_file_size.py`
   passes for `BENCHMARK.md`.
3. **Gates**:
   - `uv run --no-sync pytest`, compared with the `baseline.md` failure
     list (SG-4);
   - `uv run --no-sync pytest -m temporal tests/replay` (SG-5);
   - `uv run --no-sync ruff check .`;
   - `uv run --no-sync ruff format --check .`;
   - `uv run --no-sync mypy`;
   - on the host, `python scripts/check_file_size.py`.
4. **Private-leak tests**: `uv run --no-sync pytest tests/test_private_leak.py`.
