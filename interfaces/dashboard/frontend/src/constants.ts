export const STAGES = [
  'intake',
  'constitution',
  'context',
  'requirements',
  'clarify',
  'architecture',
  'planning',
  'code',
  'review',
  'analyze',
  'qa',
  'quality_gate',
  'deploy',
  'retro',
] as const

export type StageName = (typeof STAGES)[number]

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

export const STATUS_COLORS = {
  running: '#5b9dd9',
  blocked: '#e0b050',
  failed: '#e06c55',
  done: '#4fae7f',
  quarantined: '#b98fdc',
  pending: '#2a3140',
  skipped: '#1b202b',
} as const

export const STAGE_LABELS = {
  done: 'done',
  active: 'in flight',
  blocked: 'gate open',
  failed: 'failed',
  skipped: 'skipped',
  pending: '·',
} as const
