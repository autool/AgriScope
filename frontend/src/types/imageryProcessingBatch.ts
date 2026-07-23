export type ImageryProcessingBatchStepCode =
  | 'radiometric'
  | 'atmospheric'
  | 'geometric'
  | 'clip'
  | 'enhancement'
  | 'band_products'

export interface ImageryProcessingBatchItemRequest {
  asset_code: string
  parameters: Record<string, unknown>
}

export interface ImageryProcessingBatchRequest {
  operator_code: string
  step_code: ImageryProcessingBatchStepCode
  comment: string
  items: ImageryProcessingBatchItemRequest[]
}

export interface ImageryProcessingBatchItemResult {
  asset_code: string
  asset_name: string
  step_code: ImageryProcessingBatchStepCode
  step_name: string
  source_file_uri: string
  source_checksum_sha256: string
  output_file_uri: string
  output_file_size_bytes: number
  output_checksum_sha256: string
  output_width: number
  output_height: number
  output_band_count: number
  output_dtype: string
  output_crs: string
  execution_parameters: Record<string, unknown>
  invalidated_downstream_steps: string[]
}

export interface ImageryProcessingBatchResponse {
  batch_code: string
  step_code: ImageryProcessingBatchStepCode
  step_name: string
  item_count: number
  processor_name: string
  processor_version: string
  executed_by: string
  executed_by_code: string
  executed_by_role: string
  comment: string
  created_at: string
  items: ImageryProcessingBatchItemResult[]
}

export interface ImageryProcessingBatchParameters {
  scaleFactor: number
  addOffset: number
  darkPercentile: number
  targetCrs: string
  targetResolution: number | null
  resampling: 'nearest' | 'bilinear' | 'cubic'
  boundaryCode: string
  enhancementMethod: 'percentile_stretch' | 'histogram_equalization'
  lowerPercentile: number
  upperPercentile: number
  histogramBins: number
  redBand: number
  greenBand: number
  blueBand: number
  nirBand: number
}
