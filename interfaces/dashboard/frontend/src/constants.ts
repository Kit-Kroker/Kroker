export const ARTIFACTS = [
  'IdeaBrief',
  'Constitution',
  'CodebaseMap',
  'Requirements',
  'Clarifications',
  'Architecture',
  'TaskPlan',
  'CodeArtifact',
  'ReviewReport',
  'AnalysisReport',
  'TestReport',
  'GateReport',
  'DeployReport',
  'RunSummary',
] as const

export const STATUS_KINDS = [
  'running',
  'blocked',
  'failed',
  'done',
  'quarantined',
  'pending',
  'skipped',
] as const

export type StatusKind = (typeof STATUS_KINDS)[number]
