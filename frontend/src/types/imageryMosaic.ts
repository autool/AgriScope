import type { BoundaryProperties, GeoJsonFeature } from '@/types/workbench'

export type ImageryMosaicStepCode =
  | 'geometric'
  | 'clip'
  | 'enhancement'
  | 'band_products'

export type ImageryMosaicColorBalanceMethod = 'none' | 'mean_std'
export type ImageryMosaicBlendMethod = 'first' | 'mean'
export type ImageryMosaicResamplingMethod = 'nearest' | 'bilinear' | 'cubic'

export interface ImageryMosaicSource {
  asset_code: string
  asset_name: string
  step_code: ImageryMosaicStepCode
  step_name: string
  source_uri: string
  source_size_bytes: number
  source_sha256: string
  source_crs: string
  source_width: number
  source_height: number
  source_band_count: number
  band_descriptions: Array<string | null>
  bounds_wgs84: number[] | null
  balance_statistics: Record<string, unknown>
}

export interface ImageryMosaicJob {
  job_code: string
  job_name: string
  boundary_code: string
  boundary_name: string
  target_crs: string
  target_resolution: number
  color_balance_method: ImageryMosaicColorBalanceMethod
  blend_method: ImageryMosaicBlendMethod
  resampling_method: ImageryMosaicResamplingMethod
  coverage_threshold: number
  coverage_ratio: number
  meets_coverage: boolean
  boundary_pixel_count: number
  covered_pixel_count: number
  source_count: number
  raster_width: number
  raster_height: number
  band_count: number
  dtype: string
  original_filename: string
  file_size_bytes: number
  checksum_sha256: string
  bounds_wgs84: number[]
  manifest: Record<string, unknown>
  created_by: string
  created_by_code: string
  created_by_role: string
  created_at: string
  inputs: ImageryMosaicSource[]
  artifact_verified: boolean
  artifact_error: string | null
  download_url: string | null
}

export interface ImageryMosaicOverview {
  max_output_pixels: number
  available_sources: ImageryMosaicSource[]
  jobs: ImageryMosaicJob[]
}

export interface ImageryMosaicSourcePayload {
  asset_code: string
  step_code: ImageryMosaicStepCode
}

export interface ImageryMosaicCreatePayload {
  job_code: string
  job_name: string
  boundary_code: string
  target_crs: string
  target_resolution: number
  color_balance_method: ImageryMosaicColorBalanceMethod
  blend_method: ImageryMosaicBlendMethod
  resampling_method: ImageryMosaicResamplingMethod
  coverage_threshold: number
  sources: ImageryMosaicSourcePayload[]
  operator_code: string
  comment: string
}

export type ImageryMosaicBoundaryFeature = GeoJsonFeature<BoundaryProperties>
