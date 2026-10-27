# Round 019 pre-flight baseline

Captured 2026-10-27 at HEAD8 `c85d0500` (branch `019-glm52-arm-retirement`,
base `6ba483a6`), before any round edit outside the planning artifacts.
Container recipe: quickstart §1 (`r019-verify`, throwaway, worktree at
`/app`, runs root read-only, `SDLC_PRIVATE_CASES_ROOT=/srv/private-cases`).

## §Catalog

Read-only probe of `kroker-worker-1:/root/.cache/opencode/models.json`
(quickstart §2.1), 2026-10-27. The seven `zai-coding-plan` rows:

| model | status |
|---|---|
| glm-4.7 | deprecated |
| glm-5-turbo | deprecated |
| glm-5.2 | deprecated |
| glm-5.2-highspeed | deprecated |
| glm-5.3 | None (live) |
| glm-5.3-flash | None (live) |
| glm-5.3-highspeed | None (live) |

`glm-5.3` and `glm-5.3-flash` are both live: **SG-6 does not fire**; Q0=A
stands.

## §Manifest

`baseline-records.sha256` (beside this file) lists **1033 files** under
`D:\own\Kroker\runs\benchmarks`, one `<sha256>  <forward-slash relative
path>` per line, sorted by path, format identical to the 017 precedent
(first entries byte-identical). Written host-side, read-only, via a
scratchpad script run with `python -I`.

## §Records

From `git show HEAD:benchmarks/cases/<id>/acceptance.yaml` (repo) and
`git -C D:\own\sdlc-private-cases show HEAD:cases/theatre-box-office/acceptance.yaml`
(private), before any edit. These values feed the FR-006 comment blocks
(data-model §1).

### cat-cafe-monitoring (repo)

- verdict `provisional`, reason `null`, note `null`
- separation strong `zai-coding-plan-glm-5.3-flash`, mean
  `0.8333333333333334`, run_ids
  `["bench-cat-cafe-monitoring-1792148180/cat-cafe-monitoring#opencode#zai-coding-plan-glm-5.3-flash"]`
- separation weak `zai-coding-plan-glm-5.2`, mean `0.4722222222222222`,
  run_ids
  `["bench-cat-cafe-monitoring-1792137753/cat-cafe-monitoring#opencode#zai-coding-plan-glm-5.2"]`
- not_comparable `10`
- oracle_id `sha256:f9a25268b472a6c0f0c4a475082b19b0e63e3450fbeb12519b537defc2643f28`
- kroker_commit `58678268`

### deveval-geotext (repo)

- verdict `rejected`, reason `no_separation`, note
  `strong 0.2222, weak 0.7778, margin -0.5556`
- separation strong `zai-coding-plan-glm-5.3-flash`, mean
  `0.2222222222222222`, run_ids
  `["bench-deveval-geotext-1792161325/deveval-geotext#opencode#zai-coding-plan-glm-5.3-flash"]`
- separation weak `zai-coding-plan-glm-5.2`, mean `0.7777777777777778`,
  run_ids
  `["bench-deveval-geotext-1792089644/deveval-geotext#opencode#zai-coding-plan-glm-5.2"]`
- not_comparable `0`
- oracle_id `sha256:4d3ae74ac105a1c078a68c4344ddd53d45b19234f0a1667e8cf2f4e0821c2d87`
- kroker_commit `58678268`

### deveval-readtime (repo)

- verdict `rejected`, reason `no_separation`, note
  `strong 0.2500, weak 0.1667, margin 0.0833`
- separation strong `zai-coding-plan-glm-5.3-flash`, mean `0.25`,
  run_ids
  `["bench-deveval-readtime-1792171942/deveval-readtime#opencode#zai-coding-plan-glm-5.3-flash"]`
- separation weak `zai-coding-plan-glm-5.2`, mean `0.16666666666666666`,
  run_ids
  `["bench-deveval-readtime-1792067990/deveval-readtime#opencode#zai-coding-plan-glm-5.2"]`
- not_comparable `0`
- oracle_id `sha256:0c758d2b7acb55184faa8ca04d45e77aae606a4b39dac6236662bd81f6b8248a`
- kroker_commit `58678268`

### deveval-lice (repo)

- verdict `rejected`, reason `reference`, note
  `30/31 oracle tests passed; failed: oracle/unit_tests/test_lice.py::test_package_template`
- separation `null` (offline accept; the online re-label computes one —
  data-model §2 lice correction)
- not_comparable — (no separation object)
- oracle_id `sha256:31d9154a2bf518c9f3b35dad0f57cad750e1e73e6b8213edb678ae23a54a8f8e`
- kroker_commit `unknown`

### deveval-hone (repo, parked)

- verdict `not_assessed`, reason `null`, note
  `separation not assessed for parked case`
- separation strong `null`, weak `null` (sentinel), not_comparable `0`
- oracle_id `sha256:ef8df118bef3343bbadac78cc645bac452049e09b77e5cb6b3ac61109cd78df9`
- kroker_commit `64cd9f546834ec57c6be92c88ec0c31e98d2661d`

### deveval-particle-swarm-optimization (repo, parked)

- verdict `not_assessed`, reason `null`, note
  `separation not assessed for parked case`
- separation strong `null`, weak `null` (sentinel), not_comparable `0`
- oracle_id `sha256:b4555d5c2c03e1e55dd23f7beba81d1b2dcd7afeb63e2571cfd0d922e8770d58`
- kroker_commit `64cd9f546834ec57c6be92c88ec0c31e98d2661d`

### deveval-stocktrends (repo, parked)

- verdict `not_assessed`, reason `null`, note
  `separation not assessed for parked case`
- separation strong `null`, weak `null` (sentinel), not_comparable `0`
- oracle_id `sha256:5f9285b290465db9f7089612ef7012ca45e17c031706e6042a9fc93858d9c5a9`
- kroker_commit `64cd9f546834ec57c6be92c88ec0c31e98d2661d`

### theatre-box-office (private store)

- verdict `rejected`, reason `no_separation`, note
  `strong 0.0179, weak 0.0179, margin 0.0000`
- separation strong `zai-coding-plan-glm-5.3-flash`, mean
  `0.017857142857142856`, run_ids
  `["bench-theatre-box-office-1792347162/theatre-box-office#opencode#zai-coding-plan-glm-5.3-flash"]`
- separation weak `zai-coding-plan-glm-5.2`, mean `0.017857142857142856`,
  run_ids
  `["bench-theatre-box-office-1792359046/theatre-box-office#opencode#zai-coding-plan-glm-5.2"]`
- not_comparable `0`
- oracle_id `sha256:a66c0c4e7cdad8b34219d8c271f84b8518904df84c7c5807c2e6ff45c1da40f8`
- kroker_commit `1e697522`

## §Corpus

Full output of `uv run --no-sync python -m sdlc.cli benchmark corpus` in
the quickstart §1 container (both roots), 2026-10-27:

```
Case                                   Role     Visibility  Exposure     Verdict        Reason         Stale
-------------------------------------------------------------------------------------------------------------------
add-login-greenfield                   probe    private     repo_public  -              -              not assessed
cat-cafe-monitoring                    corpus   private     repo_public  provisional    -              no
crew-probe                             probe    private     repo_public  -              -              not assessed
deveval-geotext                        corpus   public      repo_public  rejected       no_separation  yes
deveval-hone                           parked   public      repo_public  not_assessed   -              yes
deveval-lice                           corpus   public      repo_public  rejected       reference      yes
deveval-particle-swarm-optimization    parked   public      repo_public  not_assessed   -              yes
deveval-readtime                       corpus   public      repo_public  rejected       no_separation  yes
deveval-stocktrends                    parked   public      repo_public  not_assessed   -              yes
theatre-box-office                     corpus   private     isolated     rejected       no_separation  no
todo-api-greenfield                    smoke    private     repo_public  -              -              not assessed

Parked cases:
  deveval-hone: parked (-)
  deveval-particle-swarm-optimization: parked (-)
  deveval-stocktrends: parked (-)

1 of 8 accepted or provisional, 1 of 2 private
private store: 1 case(s) at /srv/private-cases
```

Expected tally confirmed: **`1 of 8 accepted or provisional`**.

Note on pre-existing staleness (recorded, not a stop): six rows
(geotext, hone, lice, particle-swarm, readtime, stocktrends) already
print `Stale: yes` at base from **oracle drift** — the current oracle
dirs no longer hash to the `oracle_id` those older records carry. The
same output was confirmed on the main checkout (live dev container,
read-only), so it is the true pre-round state, not a worktree artifact.
D-6's "no row flips today" claim is about the new **arm-drift** rule:
none of these rows may change when FR-009 lands (the Phase 3 checkpoint
diff against this section must be empty). The T027/T031 re-labels
rewrite each touched record against the current oracle, which is what
makes contract §3's zero-stale end state reachable.

## §Fast tier

`uv run --no-sync pytest` (fast tier, addopts deselection applied):
**12 failed, 6571 passed, 19 skipped, 275 deselected** in 26m13s
(exit 1).

Environment note (recorded deviation): the sanctioned `/app` invocation
runs at ~6.6s/test on this host's bind mount (projected ~14h; a first
attempt was killed at 7% — its partial showed one `F` around the 6%
mark that the completed run below does not reproduce; treated as a
flake of the aborted run, consistent with the known notify-flake
class). The recorded run executed from `/work`, a container-local
`git archive HEAD` copy of the same tree (`c85d0500`) — byte-identical
tracked content, same venv, `pythonpath = [".", "src"]` resolving to
the copy. All mutating round commands (accept) still run against
`/app`.

The 12 failing node ids, classified:

Genuine pre-existing failures on main (content, reproduce in any
environment):

1. `tests/test_benchmark_acceptance_stalled.py::test_sc003_recompute_stored_acceptance`
2. `tests/test_benchmark_corpus.py::test_committed_records_match_their_cases`
3. `tests/test_deveval_corpus.py::test_imported_cases_state_role_and_visibility[deveval-hone]`
4. `tests/test_deveval_corpus.py::test_imported_cases_state_role_and_visibility[deveval-particle-swarm-optimization]`
5. `tests/test_deveval_corpus.py::test_imported_cases_state_role_and_visibility[deveval-stocktrends]`
6. `tests/test_todo_api_case_loads.py::test_todo_api_case_file_exists_and_loads`
7. `tests/test_prompt_migration.py::test_prompt_shas_did_not_move`

- 1–2 are the oracle-drift condition visible in §Corpus (records'
  `oracle_id` ≠ current oracle hash for the six drifted cases). This
  round's T027/T031 re-labels re-stamp those records and are expected
  to turn both green.
- 3–6 are stale tests from earlier rounds: 3–5 still assert `corpus`
  for the three cases round 017 parked (hone, pso, stocktrends);
  6 still asserts 1 cell for todo-api-greenfield, which round 017
  re-paired to two arms. **Bug-crew candidates** (main defects outside
  this round's items, plan rule 5: reported, not fixed here).
- 7 asserts pre-migration prompt SHAs that later prompt edits no
  longer satisfy. Same bug-crew class.

Environment artifacts of the in-container run (git cannot resolve the
worktree's `.git` pointer — a Windows path — per research D-5; plus one
timing test):

8. `tests/graph/test_graph_store_root.py::test_the_default_root_is_the_same_from_every_cwd_of_this_worktree`
9. `tests/test_plans_are_tracked.py::test_superpowers_scratch_is_still_ignored`
10. `tests/test_prompt_gate.py::test_unchanged_prompt_passes_without_calling_a_model`
11. `tests/test_promptfoo_provider.py::test_resolve_instructions_git_ref_reads_from_git`
12. `tests/test_promptfoo_provider.py::test_provider_imports_fast_enough_for_the_promptfoo_worker`

SG-4 comparisons at T013/T042 are against this list: any failure not
listed here (and not a planned test edit) fires the guard.

## §Replay

`uv run --no-sync pytest -m temporal tests/replay`:
**34 passed, 21 skipped, 183 deselected** in 4m38s — green, exit 0.
This is the pre-flip state SG-5 protects: the gate must still be green
after the T012 test-role flip.
