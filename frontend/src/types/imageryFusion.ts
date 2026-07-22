export type ImageryFusionResamplingMethod = 'bilinear' | 'cubic'

export interface ImageryFusionSource {
  asset_code: string
  asset_name: string
  sensor_type: string
  acquired_at: string
  data_status: string
  source_uri: string | null
  source_size_bytes: number | null
  source_sha256: string | null
  source_crs: string | null
  source_width: number | null
  source_height: number | null
  source_band_count: number | null
  resolution_x: number | null
  resolution_y: number | null
  band_descriptions: Array<string | null>
  product_identity: string | null
  reflectance_quantity: string | null
  radiometric_calibration_applied: boolean
  multispectral_eligible: boolean
  multispectral_reason: string | null
  panchromatic_eligible: boolean
  panchromatic_reason: string | null
}

export interface ImageryFusionCreatePayload {
  job_code: string
  job_name: string
  multispectral_asset_code: string
  panchromatic_asset_code: string
  multispectral_band_indexes: number[]
  panchromatic_band_index: number
  resampling_method: ImageryFusionResamplingMethod
  minimum_overlap_ratio: number
  minimum_spectral_correlation: number
  minimum_spatial_detail_gain: number
  gain_limit: number
  operator_code: string
  comment: string
}

export interface ImageryFusionJob {
  job_code: string
  job_name: string
  multispectral_asset_code: string
  multispectral_asset_name: string
  panchromatic_asset_code: string
  panchromatic_asset_name: string
  multispectral_band_indexes: number[]
  panchromatic_band_index: number
  algorithm_code: string
  algorithm_version: string
  resampling_method: string
  overlap_ratio: number
  spectral_correlations: number[]
  minimum_spectral_correlation: number
  mean_spectral_correlation: number
  spatial_detail_gain: number
  output_crs: string
  output_resolution_x: number
  output_resolution_y: number
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
  artifact_verified: boolean
  artifact_error: string | null
  download_url: string | null
}

export interface ImageryFusionOverview {
  max_output_pixels: number
  sources: ImageryFusionSource[]
  jobs: ImageryFusionJob[]
}
