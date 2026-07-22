export type ImageryHistoryDataStatus = 'operational' | 'demo'
export type ImageryCoverageStatus = 'none' | 'partial' | 'complete'
export type ImageryTraceSeverity = 'success' | 'info' | 'warning' | 'error'
export type ImageryTraceEventType =
  | 'asset_imported'
  | 'demo_notice'
  | 'source_file_invalid'
  | 'cloud_threshold_exceeded'
  | 'required_step_pending'
  | 'step_completed'
  | 'step_artifact_invalid'
  | 'artifact_superseded'

export interface ImageryHistoryBoundary {
  boundary_code: string
  boundary_name: string
  boundary_level: 'city' | 'district'
  parent_code: string | null
  source_name: string
  source_version: string | null
  source_updated_at: string | null
}

export interface ImageryHistoryAsset {
  asset_code: string
  asset_name: string
  sensor_type: string
  acquired_at: string
  cloud_cover: number | null
  resolution_m: number | null
  processing_level: string | null
  data_status: ImageryHistoryDataStatus
  file_verified: boolean
  file_error: string | null
  checksum_sha256: string | null
  crs: string | null
  required_step_count: number
  verified_required_step_count: number
  processing_completion_rate: number
  covered_prefecture_count: number
  covered_county_count: number
  province_coverage_percent: number
  issue_count: number
  is_latest_operational: boolean
}

export interface ImageryCoverageCell {
  asset_code: string
  prefecture_code: string
  prefecture_name: string
  county_code: string
  county_name: string
  county_area_ha: number
  covered_area_ha: number
  coverage_percent: number
  coverage_status: ImageryCoverageStatus
}

export interface ImageryTraceEvent {
  event_code: string
  asset_code: string
  asset_name: string
  occurred_at: string
  event_type: ImageryTraceEventType
  severity: ImageryTraceSeverity
  title: string
  detail: string
  step_code: string | null
  evidence_uri: string | null
  evidence_sha256: string | null
}

export interface ImageryHistoryOverview {
  project_code: string
  generated_at: string
  asset_count: number
  operational_asset_count: number
  verified_operational_asset_count: number
  prefecture_count: number
  county_count: number
  time_start: string | null
  time_end: string | null
  boundaries: ImageryHistoryBoundary[]
  assets: ImageryHistoryAsset[]
  coverage_cells: ImageryCoverageCell[]
  trace_events: ImageryTraceEvent[]
}
