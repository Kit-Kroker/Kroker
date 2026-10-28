import type { GateItem, Run } from '../types'

// 018 T044: the decision-card seeds. The tool-approval and budget gates are
// ALWAYS-ON inbox items now (their cards are the V4/V6 contract surfaces;
// the old opt-in switch retired with CONSOLE-29's old test). The closed run
// carries R-4's gate history directly — approve for an approved gate,
// reject with 'not approved' for a non-approval.

export const TOOL_APPROVAL_ITEM: GateItem = {
  id: 'tool#1',
  type: 'gate',
  gate: 'tool_approval',
  runId: 'feature-graph-demo',
  round: 1,
  age: '12m',
  title: 'Tool approval — production shell step',
  body: 'pytest -q deploy/ — the step wants to run the deployment suite against production.',
}

export const BUDGET_ITEM: GateItem = {
  // The seeded budget run has budget 20, one crossing approved (limit now
  // 40); this second crossing is round 2.
  id: 'budget#2',
  type: 'gate',
  gate: 'budget',
  runId: 'feature-graph-demo',
  round: 2,
  age: '1m',
  title: 'Budget (round 2) — graph demo',
  body: 'Run cost $40.2000 >= budget $40.00',
}

export const CLOSED_GATES_RUN: Run = {
  id: 'feature-closed-gates',
  title: 'Closed with a gate history',
  mode: 'brownfield',
  repo: 'git@github.com:acme/graph-demo',
  activeStages: [],
  stageMarks: null,
  status: 'done',
  blocker: '',
  cost: 4.1,
  budget: null,
  roles: [],
  budgetThreshold: null,
  budgetCounted: null,
  budgetCrossings: 0,
  budgetNotice: null,
  age: '6h 20m',
  // R-4 (mapClosed's rule, represented directly on the mock's Run): a
  // closed run's gates are its decision history; a non-approval reads
  // 'not approved'.
  decisions: [
    { ts: '08:40', gate: 'architecture r1', outcome: 'approve', comment: '', decider: 'sam' },
    { ts: '09:55', gate: 'merge r1', outcome: 'reject', comment: 'not approved', decider: 'policy (auto)' },
  ],
  projectKey: null,
}

// 018 T033 (moved here by T044): the Observe outcome-fixture runs. Their
// graph-state scripts live in mock/graph.ts over the recorded projections;
// these rows are what the fleet and the rail see.
export const HALTED_RUN: Run = {
  id: 'feature-halted-demo',
  title: 'Halted at the code node',
  mode: 'greenfield',
  repo: 'git@github.com:acme/graph-demo',
  activeStages: [],
  stageMarks: null,
  status: 'failed',
  blocker: '',
  cost: 1.2,
  budget: null,
  roles: [],
  budgetThreshold: null,
  budgetCounted: null,
  budgetCrossings: 0,
  budgetNotice: null,
  age: '1h 05m',
  decisions: [],
  projectKey: null,
}

export const ESCALATED_RUN: Run = {
  id: 'feature-escalated-demo',
  title: 'Escalated after revise exhaustion',
  mode: 'greenfield',
  repo: 'git@github.com:acme/graph-demo',
  activeStages: [],
  stageMarks: null,
  status: 'failed',
  blocker: '',
  cost: 2.0,
  budget: null,
  roles: [],
  budgetThreshold: null,
  budgetCounted: null,
  budgetCrossings: 0,
  budgetNotice: null,
  age: '3h 40m',
  decisions: [],
  projectKey: null,
}

export const MULTISINK_RUN: Run = {
  id: 'feature-multisink-demo',
  title: 'Completed at two sinks',
  mode: 'greenfield',
  repo: 'git@github.com:acme/graph-demo',
  activeStages: [],
  stageMarks: null,
  status: 'done',
  blocker: '',
  cost: 3.4,
  budget: null,
  roles: [],
  budgetThreshold: null,
  budgetCounted: null,
  budgetCrossings: 0,
  budgetNotice: null,
  age: '2h 30m',
  decisions: [],
  projectKey: null,
}

export const RETIRED_RUN: Run = {
  id: 'feature-retired-demo',
  title: 'Retention expired',
  mode: 'greenfield',
  repo: 'git@github.com:acme/graph-demo',
  activeStages: [],
  stageMarks: null,
  status: 'running',
  blocker: '',
  cost: 0.9,
  budget: null,
  roles: [],
  budgetThreshold: null,
  budgetCounted: null,
  budgetCrossings: 0,
  budgetNotice: null,
  age: '5d',
  decisions: [],
  projectKey: null,
}
