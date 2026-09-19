# Contract — durable records and store files (E-77)

These are persisted formats read across process and code versions. The field tables live in `../data-model.md`; this file fixes the **compatibility rules**.

## BenchmarkRecord.graph (JSONL/records store)

- Optional; absent in FeatureWorkflow and pre-E-77 records. Readers treat absent as "not recorded".
- Heatmap rule (FR-017): after the unchanged per-record pass, add 1 to the fix count of `(case_id, graph.node_stage)` once per distinct `(run_id, graph.activation_id)` where `graph.fail_reentry == 1`. When no record carries `fail_reentry == 1`, the output is byte-identical to main.
- Stage rule (G2): `stage == "unknown"` iff `graph.node_stage == "unknown"`, for records inside an activation.

## RunSummary.graph_sha / RunState.graph_sha

- Optional; `summary.json` files written before E-77 parse unchanged.
- Equal to `GraphWorkflow._graph_sha` = `inp.graph.content_sha()`; never re-derived.

## Store files

- Every immutable file is content-addressed and trusted only after verification (parse, then hash == name, and for layouts `content_sha ==` the directory's sha).
- `latest` and the per-run pointer are the only mutable files. Both are written tmp + `os.replace`; a reader that sees a torn or dangling value falls back and never raises.
- `latest` has bounded retry on Windows sharing violations (`PermissionError`/`FileExistsError`: 5 attempts, backoff to about 100 ms); a final failure is logged and the saver still gets 200.
- The registry snapshot `schema` is `1`. Any load failure is "no snapshot" (FR-023). A future schema bump adds a reader; it never rewrites old files.
- The pointer file name is the run id only when it fully matches `[A-Za-z0-9._-]{1,200}`, is not `.`/`..` and has no leading `.`; otherwise no pointer is written (warning). This is a write path the dashboard reads back.
