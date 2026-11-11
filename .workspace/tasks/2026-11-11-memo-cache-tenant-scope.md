# Stage-output memo cache is not separated by tenant (021 GATE 2 item 3)

| | |
|---|---|
| From | 021 round (GATE 2 ruling 3; skeptic 6B) |
| Size | S |
| Status | open |

**What.** `_cache_root()` (`src/sdlc/memoization/cache.py:31-39`) scopes the memo cache per checkout (or `SDLC_MEMOIZATION_CACHE_ROOT`), not per tenant. `content_key` (`cache.py:42`) has no tenant term, and neither do `recall_query_hash` or 021's `snapshot_hash`. Two tenants with the default `project_bank="project:default"` (`src/sdlc/core/models.py:270`) running the same idea on one host compute identical keys, so tenant B can be served tenant A's cached stage output.

**Why it matters.** It violates FR-1001 (`PRD.md:477-480`, "scoped to a tenant by … store prefix") and NFR-8 ("no data path SHALL exist between tenants"). It predates 021, and 021 neither widens nor fixes it. 021's snapshot files live under `<root>/<run_id>/`, so they add no cross-tenant path.

**Shape of a fix.** Scope `_cache_root()` by `SDLC_MEMORY_TENANT` (or the run's tenant), or add the tenant to the key. Cover it with the NFR-8 adversarial cross-tenant test.
