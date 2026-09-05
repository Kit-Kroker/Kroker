# E-47a capability identity — code review findings

**Date:** 2026-08-08
**Scope:** `2ea7b54..docs/oq6-capability-identity` (now merged as `f0308e9`) — 20 files, ~1889 lines
**Suite state:** 88 capability tests pass. They passed before these findings and would pass after; none of them exercise these paths.

## Verification legend

- **CONFIRMED (executed)** — reproduced by running the code against a temp SQLite DB or in-process.
- **PLAUSIBLE (read-only)** — reads correctly against the source but was not executed. Verify before acting.

Two corrections to the first pass are recorded inline at findings 3 and 5. Both changed the classification.

---

## 1. Reversed merge creates an unrecoverable identity cycle

**Severity:** HIGH · `src/sdlc/capability/corrections.py:96` · **CONFIRMED (executed)**

`_absorb` resolves `target` from `rows` — which comes from `store.load()` and therefore includes `MERGED` rows — and never checks that the target is live.

Reproduction:

```
capability merge --from BC-001 --into BC-002     # correct
capability merge --from BC-002 --into BC-001     # operator realises direction was wrong
```

The second call passes the idempotency check at line 101 (`BC-002` is still `ACTIVE` at that point), and the result is:

```
[('BC-001', 'merged', 'BC-002'), ('BC-002', 'merged', 'BC-001')]
```

Both rows are *individually* valid, so `load()` succeeds and nothing raises. The damage is at the matcher: `resolve()` excludes every `MERGED` row (`matcher.py:70`), so this capability now has **no candidate at all** and mints a brand-new id on every subsequent assessment, forever. A client following `merged_into` through the export loops infinitely.

There is no `unmerge` verb, so this is not recoverable from the CLI.

A simpler variant: `merge --from BC-003 --into BC-001` where `BC-001` is already merged silently discards the fingerprint inheritance that `corrections.py:88-91` calls "what makes the correction stick" — because the inheriting row is excluded from matching.

**Fix direction:** guard that `target.status is ACTIVE` before absorbing; follow `merged_into` to the live head, or reject with a message naming it.

---

## 2. Correction reason is validated, required, then discarded

**Severity:** MEDIUM · `src/sdlc/capability/store.py:130` · **CONFIRMED (executed)**

`apply_correction` (`corrections.py:66`) passes only `actor` and `operation` to `store.apply`. `apply` has no parameter for a reason and writes `row.status.value` into `capability_event.detail`.

A merge with `reason="THE HUMAN JUSTIFICATION"` produces:

```
('BC-001', 'system', 'resolve', 'active')
('BC-002', 'system', 'resolve', 'active')
('BC-001', 'maks',   'merge',   'merged')
('BC-002', 'maks',   'merge',   'active')
```

The reason appears in no column.

This defeats the module's stated purpose. `corrections.py:3-6` says `reason` "is retained as a calibration signal"; `cli.py:12` repeats it; `IdentityCorrection._audited` rejects a blank one with *"an unattributed override is not an audited one."* It is validated, required at the CLI, and thrown away. The `detail` column exists and defaults to `''`.

**Fix direction:** thread `reason` through `apply` into `detail`.

---

## 3. Renormalization gives a weak-only overlap full weight

**Severity:** MEDIUM · `src/sdlc/capability/fingerprint.py:56` · **behavior CONFIRMED (executed); defect status is a spec question**

> **Correction to the first pass.** I labelled this CONFIRMED, which conflated *the behavior reproduces* with *the behavior is wrong*. Only the first is established. Your read is right: the spec's renormalization rationale explicitly targets the strong-tier-absent case and is silent on weak-only, so whether this is a defect or an under-specified design is a decision, not an observation.

Executed:

```python
a = {contract: ["POST /a"], locational: ["src/core/x.py"]}
b = {locational: ["src/core/x.py"]}
score(a, b) == (1.0, {LOCATIONAL: 1.0})  # T_MATCH = 0.55
```

`shared` keeps only tiers non-empty on both sides and `denominator` renormalizes over exactly those, with no floor on evidence quality. So `LOCATIONAL` — the tier the design calls "the cheapest thing in a repo to change" — is worth 1.00 whenever it is the only overlap. A new internal capability living in the same directory as a stored one, sharing no routes, tables, symbols or tests, inherits the stored id.

This is the exact mirror of `test_absent_tier_is_renormalized_away_not_scored_zero`, which proves renormalization *helps* when Contract is missing. Nothing tests the case where the same rule hurts.

**Three defensible resolutions** — this needs a decision, not a patch:

1. **Evidence floor.** Require at least one non-Locational shared tier before a match is eligible.
2. **Cap the renormalized weight** of any single tier, so no lone tier can reach 1.0.
3. **Declare it intended** and raise `T_MATCH`, accepting that co-location is real evidence in some codebases.

I lean to (1): it is the smallest change that preserves the spec's stated intent (don't punish internal capabilities) while denying the weakest signal sole authority. But it is a spec amendment either way and should be recorded as one.

---

## 4. Duplicate `local_key` gives two capabilities one `bc_id`

**Severity:** MEDIUM · `src/sdlc/capability/matcher.py:72` · **CONFIRMED (executed)**

`scored` is keyed `(local_key, bc_id)` and `assigned` by `local_key`, but nothing validates that `local_key` is unique across `proposed`, and the attachment loop at line 93 iterates `proposed` rather than the keys.

Executed with two entries both using `local_key="dup"`:

```
[('dup', 'BC-001', 'matched'), ('dup', 'BC-001', 'matched')]
```

Two distinct capabilities, one id — the precise one-to-one violation `assign()` exists to prevent, reached by bypassing it.

`local_key` is documented as "the caller's handle for this assessment only" and is produced by discover (E-48), which does not exist yet. Nothing upstream enforces uniqueness, so the first integration inherits this silently.

**Fix direction:** raise at the top of `resolve()` on a duplicate `local_key`. Fail loudly; there is no sensible recovery.

---

## 5. Self-merge reports success while doing nothing

**Severity:** LOW · `src/sdlc/capability/corrections.py:105` · **CONFIRMED (executed)**

> **Correction to the first pass.** An escalation was raised that a self-merge writes an invalid row and makes the project unreadable on next `load()`. **That does not reproduce.** `_absorb` returns `[absorbed, survivor]`; `apply` upserts in list order; for a self-merge both are `BC-001`, so `survivor` — built from the original target row — overwrites `absorbed` in the same transaction. Disk ends at `('BC-001','active',None)` and `load()` succeeds. This is a no-op, not data loss.

`model_copy(update=...)` does not re-run Pydantic validation, so the `"{bc_id} cannot be merged into itself"` guard at `models.py:100` — which `test_merged_into_must_not_be_self` covers — is bypassed.

`capability merge --from BC-001 --into BC-001` returns exit 0, prints `merge: BC-001 -> registry_version N`, bumps the version, and writes a spurious `merged` event, while the row is unchanged. The operator is told a correction happened that did not.

**Why fix it anyway:** the invalid object is real in memory and survives only by write ordering that nothing asserts. Reorder that return list or add an early return and it becomes genuine corruption. Re-validating (`CapabilityIdentity.model_validate(absorbed.model_dump())`) or an explicit `source is target` guard removes the latency.

---

## 6. A partition naming every member leaves an empty husk

**Severity:** LOW · `src/sdlc/capability/corrections.py:128` · **PLAUSIBLE (read-only)**

The guard rejects a partition that matched *nothing*; it does not check that anything remains in `kept`. Splitting `BC-001{contract:["POST /a","POST /b"]}` with both members in the partition should yield `BC-001 active []` alongside the new id holding everything.

The husk can never match again — `score()` returns `None` with no shared tiers — and its export digest is identical to every other empty fingerprint.

Related, same line: a partition where only *some* members match is accepted silently, so a typo in one `--member` moves the rest and reports success.

**Fix direction:** reject a partition that empties the source; reject members that match nothing.

---

## 7. New ids minted in caller order, breaking NFR-10

**Severity:** LOW (raise if E-48 lands first) · `src/sdlc/capability/matcher.py:105` · **CONFIRMED (executed)**

`allocate()` is called inside `for p in proposed:` in submission order.

```
forward: {'x': 'BC-900', 'y': 'BC-901'}
reverse: {'y': 'BC-900', 'x': 'BC-901'}
```

`assign()` is order-independent, but minting is not. `test_resolution_is_deterministic_across_input_order` does not catch it for two compounding reasons: it compares only matched pairs, *and* all three of its proposed capabilities match the registry, so nothing is ever minted.

For an identifier the design calls client-cited and NFR-10-deterministic, allocation must key off something stable.

**Fix direction:** mint in `sorted(local_key)` order, in a pass separate from the attachment loop.

---

## 8. `apply()` ignores `row.project`

**Severity:** LOW · `src/sdlc/capability/store.py:110` · **PLAUSIBLE (read-only)**

`apply()` binds the `project` argument rather than `row.project`, so rows built for one project land in another with no error. `load()` reconstructs with the argument project, making the mismatch unobservable afterwards.

**Fix direction:** `if row.project != project: raise`. Costs nothing; converts a silent cross-project write into a failure.

---

## 9. Export digest omits `collected`

**Severity:** LOW · `src/sdlc/capability/export.py:29` · **PLAUSIBLE (read-only)**

`fingerprint_sha256` hashes only the tier members. Two rows with identical tiers but different collection states — one `MEASURED`, one `NOT_COLLECTED`, a pair the design treats as fundamentally distinguishable — produce the same digest, and every empty-or-uncollected fingerprint hashes identically.

The export's stated job 3 ("a differing hash means the shape moved") survives. The converse a client actually relies on — same hash means nothing changed — cannot distinguish "measured and empty" from "we could not measure." That is the conflation `measurement.py` exists to prevent, reappearing in the client-facing artifact.

**Fix direction:** include the collection state in the hashed canonical form.

---

## 10. `allocator`'s never-reuse invariant is not enforceable as written

**Severity:** LOW now, HIGH at first integration · `src/sdlc/capability/store.py:143` · **PLAUSIBLE (read-only)**

`allocator()` documents "never returns an id that has ever been allocated for this project." `next_ordinal` only advances inside `apply()`, via `_max_ordinal(rows) + 1` over whatever rows the caller passes.

But `resolve()` returns minted ids inside `IdentityAttachment` objects, **not** as `CapabilityIdentity` rows. A caller that persists only the matched and retired rows leaves `next_ordinal` unmoved and re-mints the same BC ids for different capabilities on the next run — breaking invariant 1, the one the whole surrogate-key design rests on.

Nothing outside `src/sdlc/capability/` imports `resolve()` today, so this is latent. E-48 is the first caller and is the one that will get it wrong.

**Fix direction:** reserve the ordinal at mint time inside the allocator, or have `apply` take an explicit high-water mark.

---

## Cleared on inspection

- The `BEGIN IMMEDIATE` / `ROLLBACK` block in `store.apply` is correct — `BEGIN` sits outside the `try`, so the handler cannot fire without an open transaction.
- `_best_near_miss` does not filter by `t_match` despite its docstring, but the branch is unreachable: any unassigned `local_key` with an above-threshold pair necessarily has that pair's `bc_id` in `claimed_ids`, so `_lost_above_threshold` returns first.
- `_needs_temporal_client` short-circuits before touching `args.target` / `args.sched_cmd` for `capability`; `raise SystemExit(0)` on the success path is fine.
- Dead but harmless: `RetiredReason.ABSORBED`, `AttachMethod.FORCED_BY_CORRECTION`, `IdentityNotFoundError` are defined and never used.

---

## Suggested order

1. **#1** — the only finding that destroys identity irrecoverably, reachable by an ordinary operator mistake, with no CLI escape.
2. **#4**, then **#3** — the two that can hand a client-cited identifier to the wrong capability. #3 needs a spec decision first.
3. **#10** — before E-48 exists, not after.
4. **#2**, **#5**, **#6**, **#7**, **#8**, **#9** — independent, small, no ordering between them.

Each fix wants an adversarial test at the seam, not a restatement of the happy path. The 88 passing tests are the evidence that the current surface does not reach any of this.
