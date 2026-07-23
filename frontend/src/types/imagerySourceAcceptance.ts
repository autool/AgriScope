export type ImagerySourceProcessingLevel = 'L2A' | 'L2'

export interface ImagerySourceAcceptanceBatchItemRequest {
  asset_code: string
  expected_processing_level: ImagerySourceProcessingLevel
}

export interface ImagerySourceAcceptanceBatchRequest {
  operator_code: string
  confirm_no_algorithm_execution: true
  justification: string
  items: ImagerySourceAcceptanceBatchItemRequest[]
}

export interface ImagerySourceAcceptanceBatchItem {
  asset_code: string
  asset_name: string
  expected_processing_level: ImagerySourceProcessingLevel
  source_profile: string
  processor_version: string
  accepted_steps: string[]
  source_file_uri: string
  source_file_size_bytes: number
  source_checksum_sha256: string
}

export interface ImagerySourceAcceptanceBatchResponse {
  acceptance_code: string
  item_count: number
  accepted_step_count: number
  imported_by: string
  imported_by_code: string
  imported_by_role: string
  justification: string
  created_at: string
  items: ImagerySourceAcceptanceBatchItem[]
}
