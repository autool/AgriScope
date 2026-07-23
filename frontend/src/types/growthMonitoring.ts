import type { GeoJsonFeatureCollection } from '@/types/workbench'

export interface GrowthMonitoringSource {
  asset_code: string
  asset_name: string
  acquired_at: string
  data_status: string
  source_uri: string | null
  source_size_bytes: number | null
  source_sha256: string | null
  ndvi_band_index: number | null
  eligible: boolean
  unavailable_reason: string | null
}

export interface GrowthMonitoringRun {
  run_code: string
  run_name: string
  baseline_asset_code: string
  baseline_asset_name: string
  baseline_acquired_at: string
  current_asset_code: string
  current_asset_name: string
  current_acquired_at: string
  poor_delta_threshold: number
  good_delta_threshold: number
  minimum_zone_area_ha: number
  minimum_spatial_coverage_ratio: number
  minimum_valid_pixel_ratio: number
  algorithm_code: string
  algorithm_version: string
  task_plot_count: number
  task_updated_at: string
  output_crs: string
  output_resolution_x: number
  output_resolution_y: number
  raster_width: number
  raster_height: number
  bounds_wgs84: number[]
  task_farmland_area_ha: number
  common_footprint_farmland_area_ha: number
  spatial_coverage_ratio: number
  common_footprint_mask_pixel_count: number
  valid_pixel_count: number
  valid_pixel_ratio: number
  poor_pixel_count: number
  normal_pixel_count: number
  good_pixel_count: number
  anomaly_zone_count: number
  anomaly_area_ha: number
  classification_filename: string
  classification_size_bytes: number
  classification_sha256: string
  anomaly_filename: string
  anomaly_size_bytes: number
  anomaly_sha256: string
  manifest: Record<string, unknown>
  created_by: string
  created_by_code: string
  created_by_role: string
  comment: string
  created_at: string
  task_snapshot_current: boolean
  stale_reason: string | null
  classification_verified: boolean
  anomaly_verified: boolean
  source_verified: boolean
  source_error: string | null
  artifact_error: string | null
  classification_download_url: string | null
  anomaly_download_url: string | null
}

export interface GrowthMonitoringOverview {
  project_code: string
  task_code: string
  max_output_pixels: number
  sources: GrowthMonitoringSource[]
  runs: GrowthMonitoringRun[]
  selected_run_code: string | null
  feature_collection: GeoJsonFeatureCollection
}

export interface GrowthMonitoringCreatePayload {
  run_code: string
  run_name: string
  baseline_asset_code: string
  current_asset_code: string
  poor_delta_threshold: number
  good_delta_threshold: number
  minimum_zone_area_ha: number
  minimum_spatial_coverage_ratio: number
  minimum_valid_pixel_ratio: number
  operator_code: string
  comment: string
}

export type GrowthArtifactType = 'classification' | 'anomalies'
