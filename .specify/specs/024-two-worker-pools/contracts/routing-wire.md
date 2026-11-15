# Contract — routing on the wire

1. **W-1 (off is invisible).** With `harness_queue` absent or `None`:
   - no input payload gains a key (`exclude_if`);
   - no `ScheduleActivityTask` command carries a non-default queue;
   - the replay corpus and the golden projections are byte-identical.
2. **W-2 (on is total).** With `harness_queue = q`, every activity in `HARNESS_ACTIVITIES` is scheduled with `task_queue = q`, and every other activity with none.
   - This holds across the nine workflow types with harness-class sites: GraphWorkflow, CrewTaskWorkflow, BenchmarkWorkflow, TriageWorkflow, TidyUpWorkflow, AssessmentWorkflow, DeploymentWorkflow, MaintenanceWorkflow and MaintenanceKickWorkflow.
   - `ReflectWorkflow`, the tenth registered type, schedules only the core `reflect` activity, so it is trivially all-core.
   - Workflows and child workflows stay on the parent's own queue.
3. **W-3 (fixed at start).** `q` is read from the environment only on the client, once, at start. It travels in input, and children copy it. No workflow code reads the environment.
4. **W-4 (fail fast).** A client start path with `q` set raises `HarnessQueueUnpolled(q)` before `start_workflow`, or before `create_schedule`/`update_schedule`, if no fresh activity poller exists on `q`. The CLI prints the message and exits 2.
5. **W-5 (benchmark ids).** Benchmark workflow ids are `bench-<case_id>-<epoch_s>-<6 hex>`, so they are unique under concurrent same-second starts.
