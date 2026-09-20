# root-store-write — REGRESSION QA (chaos) findings

Seat: qa-chaos. Deliverable:
`tests/graph/test_graph_store_root_chaos.py` (19 test items across 12
tests: 17 verified RED on this worktree 2026-09-20, pre-fix, commit
6ba51ab; 2 green-by-design guards). Fix surface:
`.specify/bugs/root-store-write/assessment.md` (preferred remediation:
fail-closed relative refusal + checkout-anchored default).

## Sibling file (not mine)

`tests/graph/test_graph_store.py` sibling
`tests/graph/test_graph_store_root.py` — the happy-path RED deliverable
of the qa-happy seat (report: `.workspace/tmp/qa-happy-root-store-write-
red.md`) — is present but UNCOMMITTED at my verification time. I did not
touch, run, or commit it. Overlap is deliberate and complementary: the
happy file pins in-process CWD identity (one root per checkout from every
CWD, one store across CWDs, this-worktree linked-`.git` variant, rerun
reuse, absolute-override pinning, mechanism-neutral agree-or-refuse);
the chaos file pins the edge shapes below. The two files share no state
(both use per-test monkeypatch env hygiene).

## Chaos test inventory

| Test | Axis | RED today because | Post-fix contract |
|---|---|---|---|
| `...relative_store_env_is_refused_loudly[x\|.\|..\|./graphs]` | error path + boundary values | `Path(v).resolve()` anchors at CWD, no raise | `ValueError` naming `SDLC_GRAPH_STORE`; resolution-only, writes nothing either side |
| `test_a_windows_drive_relative_env_is_refused_like_any_relative` | boundary value (Windows) | `D:x` / `\graphs` resolve quietly (drive-/drive-relative anchoring) | classified as relative → refused; never an excuse to touch `<drive>\` |
| `...relative_artifact_or_export_env_is_refused_for_the_store[ARTIFACT\|EXPORT]` | error path | `graphs` sibling silently placed in CWD (probe 4) | refusal naming the refused var; store-side only |
| `...explicit_relative_root_is_refused[x\|.]` + Windows variant | error path (constructor) | `GraphStore("x").root == <cwd>/x` (probe 6) | `ValueError`; every existing caller passes absolute tmp_path, so nothing else changes |
| `...blank_env_value_stays_unset_and_never_litters_the_cwd[3 vars]` | boundary value | pin half GREEN (truthiness already skips blanks — assessment probe 5, negative finding pinned); litter half RED: `./runs` fallback drops `<cwd>/graphs/registry/...` | blank == unset exactly (never `Path("") == "."`), and no new direct child of the CWD after a default-root write |
| `test_a_relative_store_env_never_materializes_or_respawns_a_cwd_child` | stale state | `put_registry` writes `<cwd>/x/registry/<sha>.json`; deleting `x/` invites respawn (the incident) | `x` never exists as a direct child of the CWD, before and after whack-a-mole deletion |
| `test_a_stale_relative_rooted_store_is_never_adopted` | stale state | CWD-anchored root makes `get_registry` return the squatter's VALID content | a pre-fix snapshot under `<cwd>/x/` is dead weight: refused or invisible, never adopted |
| `test_concurrent_starters_from_two_cwds_converge_on_one_store` | concurrency (cross-process) | two real subprocesses root at `alpha/graphs` vs `beta/graphs` | one root from both children; a third opener from a third CWD sees both uuid-salted snapshots |
| `...two_different_checkouts_keep_two_different_stores[clone\|worktree]` | hermeticity guard | — (green by design, today and post-fix) | two checkouts never share a store; RED for the machine-global over-correction (the memo-cache bug's shape) |
| `test_a_non_repo_cwd_gets_a_namespaced_root_not_the_cwd` | boundary/stale | default root == `<cwd>/graphs` outside any repo | absolute, namespaced, CWD-independent; no CWD-child litter; two non-repo CWDs differ |

Failure signatures verified (not just counts): `DID NOT RAISE ValueError`
×10 refusal items, `{'graphs'} == set()` ×3 litter, `'x' not in ['x']`
respawn, squatter content returned, `alpha/graphs != beta/graphs`
subprocess fork, `nowhere-a/graphs` CWD anchoring. Interference check:
`tests/graph/test_graph_store.py` + this file in one run → existing 12
pass, no env/cwd bleed (monkeypatch per-test).

## Why the kinship argument carries over (hermeticity guard)

The guard is green today only vacuously — the bug itself splits stores
by CWD. Its value is against the fix's own failure mode: converging the
root by going machine-global (the exact memo-cache-root defect) would
turn it RED. The worktree variant matters for the same reason as in the
memo bug: a linked worktree shares the commit sha AND the `.git` dir
with its primary checkout, so identity keyed on anything shared
contaminates real multi-seat runs; only path-derived checkout identity
(or per-checkout storage) passes both variants.

## Why real subprocesses (the concurrency axis)

CWD is process-global, so cross-CWD concurrency is cross-process in
production — the human CLI and the dashboard are separate OS processes.
`monkeypatch.chdir` can only prove in-process bookkeeping; two
`subprocess.Popen` children started unjoined in two CWDs (each
self-clearing the three root env vars) prove the resolved root cannot
depend on the test process's own CWD state. The children genuinely race
on the converged root post-fix (mkdir + atomic replace, the Windows
retry path's purpose); assertions run only after both join, so the test
stays deterministic.

## Determinism and side effects

Every registry is uuid-salted per run: nothing an earlier run left in a
real store can flip a result. Pre-fix RED runs write only under pytest's
tmp_path. The refusal tests write nothing on either side of the fix —
by design, so the drive-anchored `\graphs` boundary value can never
cause a write to `<drive>\`. Post-fix GREEN runs will write inert salted
snapshots under the real default root (unavoidable when testing the
default), same as the memo-cache chaos precedent.

## Ruling-dependency map (for the cause gate / fix review)

- Refusal tests (env, derivation, constructor) hold under EVERY
  remediation alternative in the assessment — preferred, (a), and (b)
  all refuse relative inputs. Only the `match=` "names the var" clause
  is preferred-direction wording.
- Convergence (subprocess), blank-env litter, and non-repo anchoring
  encode the preferred DEFAULT-location direction. Alternative (a)
  (in-tree `<checkout>/graphs`) also passes them (CWDs in these tests
  are checkout SUBDIRECTORIES). The REJECTED alternative (b) (refuse
  only, keep `./runs` default) would leave them RED — consistent with
  the assessment rejecting (b) as incomplete, noted here so a verdict
  wedge is diagnosable.
- No scope ruling is requested this time: unlike the memo-cache
  unreadable-entry edge, every test here sits on the assessed fix
  surface itself (`default_root()` / `GraphStore.__init__` resolution
  semantics), not on adjacent hardening.
