export type SupervisionSamplingMethod = 'systematic' | 'stratified_random'
export type SupervisionPlanStatus = 'active' | 'completed' | 'cancelled'
export type SupervisionInspectionStage =
  | 'imagery_processing'
  | 'plot_interpretation'
  | 'quality_control'
  | 'field_verification'
  | 'review_delivery'
export type SupervisionInspectionConclusion = 'passed' | 'conditional' | 'failed'
export type SupervisionFindingSeverity = 'minor' | 'major' | 'critical'
export type SupervisionFindingStatus =
  | 'open'
  | 'rectification_submitted'
  | 'rework_required'
  | 'closed'
export type SupervisionReinspectionResult = 'passed' | 'failed'

export interface SupervisionWorkArea {
  city_code: string
  city_name: string
  region_code: string
  region_name: string
  plot_count: number
  area_ha: number
}

export interface SupervisionEvent {
  entity_type: string
  entity_code: string
  action: string
  previous_values: Record<string, unknown>
  new_values: Record<string, unknown>
  comment: string
  operator: string
  operator_code: string
  operator_role: string
  created_at: string
}

export interface SupervisionReinspection {
  round_no: number
  result: SupervisionReinspectionResult
  comment: string
  evidence_uri: string
  inspector: string
  inspector_code: string
  inspector_role: string
  created_at: string
}

export interface SupervisionFinding {
  finding_code: string
  plot_code: string | null
  region_code: string
  region_name: string
  issue_type: string
  severity: SupervisionFindingSeverity
  description: string
  evidence_uri: string
  rework_deadline: string
  overdue: boolean
  status: SupervisionFindingStatus
  rectification_comment: string | null
  rectification_evidence_uri: string | null
  rectified_by: string | null
  rectified_by_code: string | null
  rectified_by_role: string | null
  rectified_at: string | null
  created_by: string
  created_by_code: string
  created_by_role: string
  created_at: string
  reinspections: SupervisionReinspection[]
}

export interface SupervisionInspection {
  inspection_code: string
  inspection_stage: SupervisionInspectionStage
  inspected_at: string
  conclusion: SupervisionInspectionConclusion
  evidence_uri: string
  summary: string
  inspector: string
  inspector_code: string
  inspector_role: string
  created_at: string
  findings: SupervisionFinding[]
}

export interface SupervisionCountyEvaluation {
  region_code: string
  region_name: string
  quality_score: number
  timeliness_score: number
  compliance_score: number
  overall_score: number
  grade: 'A' | 'B' | 'C' | 'D'
  comment: string
  evaluated_by: string
  evaluated_by_code: string
  evaluated_by_role: string
  evaluated_at: string
}

export interface SupervisionReport {
  report_code: string
  file_uri: string
  file_size_bytes: number
  checksum_sha256: string
  evidence_manifest: Record<string, unknown>
  generated_by: string
  generated_by_code: string
  generated_by_role: string
  generated_at: string
  download_url: string
}

export interface SupervisionPlan {
  plan_code: string
  plan_name: string
  sampling_method: SupervisionSamplingMethod
  sample_ratio: number
  minimum_per_region: number
  region_codes: string[]
  region_sample_counts: Record<string, number>
  sample_count: number
  task_plot_count_snapshot: number
  task_updated_at_snapshot: string
  planned_start_date: string
  planned_end_date: string
  status: SupervisionPlanStatus
  inspection_count: number
  finding_count: number
  open_finding_count: number
  overdue_finding_count: number
  evaluation_count: number
  created_by: string
  created_by_code: string
  created_by_role: string
  created_at: string
  updated_at: string
  inspections: SupervisionInspection[]
  county_evaluations: SupervisionCountyEvaluation[]
  report: SupervisionReport | null
  recent_events: SupervisionEvent[]
}

export interface SupervisionOverview {
  project_code: string
  task_code: string
  blockers: string[]
  metrics: {
    plan_count: number
    active_plan_count: number
    sampled_plot_count: number
    inspection_count: number
    open_finding_count: number
    overdue_finding_count: number
    completed_report_count: number
  }
  work_areas: SupervisionWorkArea[]
  plans: SupervisionPlan[]
}

export interface SupervisionSample {
  plot_code: string
  region_code: string
  region_name: string
  plot_version_snapshot: number
  selection_rank: number
  selected_at: string
}

export interface SupervisionSamplePage {
  plan_code: string
  total: number
  page: number
  page_size: number
  items: SupervisionSample[]
}

export interface SupervisionPlanCreatePayload {
  plan_code: string
  plan_name: string
  sampling_method: SupervisionSamplingMethod
  sample_ratio: number
  minimum_per_region: number
  region_codes: string[]
  planned_start_date: string
  planned_end_date: string
  operator_code: string
  comment: string
}

export interface SupervisionInspectionCreatePayload {
  inspection_code: string
  inspection_stage: SupervisionInspectionStage
  inspected_at: string
  conclusion: SupervisionInspectionConclusion
  evidence_uri: string
  summary: string
  operator_code: string
}

export interface SupervisionFindingCreatePayload {
  finding_code: string
  plot_code: string | null
  region_code: string
  issue_type: string
  severity: SupervisionFindingSeverity
  description: string
  evidence_uri: string
  rework_deadline: string
  operator_code: string
}

export interface SupervisionRectificationPayload {
  rectification_comment: string
  rectification_evidence_uri: string
  operator_code: string
}

export interface SupervisionReinspectionPayload {
  result: SupervisionReinspectionResult
  comment: string
  evidence_uri: string
  operator_code: string
}

export interface SupervisionCountyEvaluationPayload {
  quality_score: number
  timeliness_score: number
  compliance_score: number
  comment: string
  operator_code: string
}

export interface SupervisionReportGeneratePayload {
  operator_code: string
  comment: string
}

export const supervisionSamplingMethodLabels: Record<SupervisionSamplingMethod, string> = {
  systematic: '系统抽样',
  stratified_random: '县区分层随机',
}

export const supervisionStageLabels: Record<SupervisionInspectionStage, string> = {
  imagery_processing: '影像生产',
  plot_interpretation: '地块解译',
  quality_control: '质量控制',
  field_verification: '外业核查',
  review_delivery: '审核交付',
}

export const supervisionFindingStatusLabels: Record<SupervisionFindingStatus, string> = {
  open: '待整改',
  rectification_submitted: '待复检',
  rework_required: '复检未通过',
  closed: '已闭环',
}
