export type ImageryRegistrationStepCode =
  | 'geometric'
  | 'clip'
  | 'enhancement'
  | 'band_products'

export type ImageryRegistrationResamplingMethod =
  | 'nearest'
  | 'bilinear'
  | 'cubic'

export interface ImageryRegistrationSource {
  asset_code: string
  asset_name: string
  step_code: ImageryRegistrationStepCode
  step_name: string
  source_uri: string
  source_size_bytes: number
  source_sha256: string
  source_crs: string
  source_width: number
  source_height: number
  source_band_count: number
  band_descriptions: Array<string | null>
  bounds_wgs84: number[]
  data_status: string
  eligible: boolean
  eligibility_reason: string | null
}

export interface ImageryRegistrationJob {
  job_code: string
  job_name: string
  reference_asset_code: string
  moving_asset_code: string
  reference_step_code: string
  moving_step_code: string
  reference_band_index: number
  moving_band_index: number
  resampling_method: ImageryRegistrationResamplingMethod
  initial_shift_x_pixels: number
  initial_shift_y_pixels: number
  initial_offset_pixels: number
  residual_shift_x_pixels: number
  residual_shift_y_pixels: number
  residual_offset_pixels: number
  overlap_ratio: number
  peak_to_sidelobe_ratio: number
  residual_threshold_pixels: number
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

export interface ImageryRegistrationOverview {
  max_output_pixels: number
  project_positional_accuracy_pixels: number
  available_sources: ImageryRegistrationSource[]
  jobs: ImageryRegistrationJob[]
}

export interface ImageryRegistrationSourcePayload {
  asset_code: string
  step_code: ImageryRegistrationStepCode
  band_index: number
}

export interface ImageryRegistrationCreatePayload {
  job_code: string
  job_name: string
  reference: ImageryRegistrationSourcePayload
  moving: ImageryRegistrationSourcePayload
  resampling_method: ImageryRegistrationResamplingMethod
  max_initial_offset_pixels: number
  max_residual_pixels: number
  minimum_overlap_ratio: number
  minimum_peak_to_sidelobe_ratio: number
  operator_code: string
  comment: string
}
