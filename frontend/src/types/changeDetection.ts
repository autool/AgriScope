import type { ImageryRegistrationJob } from '@/types/imageryRegistration'

export type ChangeClass =
  | 'suspected_construction'
  | 'farmland_outflow'
  | 'construction_facility_change'
  | 'non_farmland_agricultural_change'
  | 'unused_land_change'
  | 'farmland_attribute_change'

export type ChangeCandidateStatus = 'pending' | 'confirmed' | 'excluded'
export type ChangeRunStatus = 'active' | 'reviewing' | 'completed' | 'cancelled'
export type CandidateChangeClass = ChangeClass | 'unclassified'
export type ChangeDiscoveryAlgorithmCode =
  | 'rgb_absolute_difference'
  | 'rgb_change_vector'

export interface ChangeDiscoveryAlgorithm {
  code: ChangeDiscoveryAlgorithmCode
  name: string
  version: string
  description: string
  score_formula: string
  default_threshold: number
  threshold_min: number
  threshold_max: number
}

export interface ChangeImagery {
  asset_code: string
  asset_name: string
  sensor_type: string
  acquired_at: string
  resolution_m: number | null
  cloud_cover: number | null
  checksum_sha256: string | null
  crs: string | null
  footprint: Record<string, unknown> | null
  file_verified: boolean
  eligible: boolean
  eligibility_reason: string | null
}

export interface ChangeDetectionEvent {
  event_type: string
  previous_values: Record<string, unknown>
  new_values: Record<string, unknown>
  comment: string
  operator: string
  operator_code: string
  operator_role: string
  created_at: string
}

export interface ChangeCandidate {
  candidate_code: string
  source_name: string
  source_uri: string
  source_version: string
  source_feature_id: string
  source_checksum_sha256: string
  import_batch_code: string
  change_class: CandidateChangeClass
  confidence: number
  area_ha: number
  evidence_uri: string
  status: ChangeCandidateStatus
  exclusion_reason: string | null
  review_comment: string | null
  reviewed_by: string | null
  reviewed_by_code: string | null
  reviewed_by_role: string | null
  reviewed_at: string | null
  imported_by: string
  imported_by_code: string
  imported_by_role: string
  created_at: string
  geometry: Record<string, unknown>
  history: ChangeDetectionEvent[]
}

export interface ChangeFeatureCollection {
  type: 'FeatureCollection'
  features: Array<{
    type: 'Feature'
    geometry: Record<string, unknown>
    properties: {
      candidate_code: string
      change_class: CandidateChangeClass
      confidence: number
      area_ha: number
      status: ChangeCandidateStatus
    }
  }>
}

export interface ChangeDetectionRun {
  run_code: string
  run_name: string
  baseline_asset_code: string
  target_asset_code: string
  registration_job_code: string
  rule_config_version: number
  rule_profile_snapshot: Record<string, unknown>
  source_snapshot: Record<string, unknown>
  task_plot_count: number
  task_updated_at_snapshot: string
  alignment_method: string
  alignment_offset_pixels: number
  alignment_overlap_ratio: number
  alignment_evidence_uri: string
  status: ChangeRunStatus
  candidate_count: number
  pending_count: number
  confirmed_count: number
  excluded_count: number
  class_counts: Record<string, number>
  created_by: string
  created_by_code: string
  created_by_role: string
  created_at: string
  updated_at: string
  candidates: ChangeCandidate[]
  feature_collection: ChangeFeatureCollection
}

export interface ChangeDetectionOverview {
  project_code: string
  task_code: string
  blockers: string[]
  discovery_algorithms: ChangeDiscoveryAlgorithm[]
  imagery: ChangeImagery[]
  registrations: ImageryRegistrationJob[]
  runs: ChangeDetectionRun[]
}

export interface ChangeRunCreatePayload {
  run_code: string
  run_name: string
  baseline_asset_code: string
  target_asset_code: string
  registration_job_code: string
  operator_code: string
}

export interface ChangeCandidateImportPayload {
  type: 'FeatureCollection'
  source_name: string
  source_uri: string
  source_version: string
  operator_code: string
  comment: string
  features: unknown[]
}

export interface ChangeCandidateImportResult {
  run_code: string
  batch_code: string
  imported_count: number
  candidate_codes: string[]
  source_checksum_sha256: string
  imported_by: string
  imported_by_code: string
  imported_by_role: string
  imported_at: string
}

export interface ChangeCandidateDiscoveryPayload {
  algorithm_code: ChangeDiscoveryAlgorithmCode
  difference_threshold: number
  min_component_pixels: number
  max_candidates: number
  operator_code: string
  comment: string
}

export interface ChangeCandidateDiscoveryResult {
  run_code: string
  batch_code: string
  algorithm_code: string
  algorithm_name: string
  algorithm_version: string
  score_formula: string
  parameters: Record<string, unknown>
  detected_count: number
  imported_count: number
  filtered_below_area_count: number
  changed_pixel_count: number
  valid_pixel_count: number
  candidate_codes: string[]
  artifact_uri: string
  artifact_sha256: string
  generated_by: string
  generated_by_code: string
  generated_by_role: string
  generated_at: string
}

export interface ChangeCandidateReviewPayload {
  decision: 'confirmed' | 'excluded'
  change_class?: ChangeClass
  exclusion_reason?: string | null
  evidence_comment: string
  reviewer_code: string
}

export interface ChangeComparisonSource {
  asset_code: string
  asset_name: string
  acquired_at: string
  checksum_sha256: string
  file_size_bytes: number
  band_indexes: [number, number, number]
}

export interface ChangeComparisonMetadata {
  run_code: string
  baseline: ChangeComparisonSource
  target: ChangeComparisonSource
  baseline_url: string
  target_url: string
  bounds_wgs84: [number, number, number, number]
  width: number
  height: number
  renderer_version: string
  stretch_ranges: Array<[number, number]>
  baseline_preview_sha256: string
  target_preview_sha256: string
  generated_at: string
}

export const CHANGE_CLASS_LABELS: Record<CandidateChangeClass, string> = {
  unclassified: '未分类变化',
  suspected_construction: '疑似建设占用',
  farmland_outflow: '耕地流出',
  construction_facility_change: '建设/设施农用地变化',
  non_farmland_agricultural_change: '非农用地农业化变化',
  unused_land_change: '未利用地变化',
  farmland_attribute_change: '耕地属性标注变化',
}
