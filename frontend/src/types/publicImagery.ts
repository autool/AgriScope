import type { ImageryAssetItem } from '@/types/workbench'
import type { ImageryBatchResponse } from '@/types/imageryBatch'

export interface PublicImagerySearchRequest {
  bbox: [number, number, number, number]
  start_date: string
  end_date: string
  max_cloud_cover: number
}

export interface PublicImageryCandidate {
  item_id: string
  acquired_at: string
  cloud_cover: number | null
  platform: string
  instrument: string
  processing_level: string
  collection_category: string | null
  wrs_path: number | null
  wrs_row: number | null
  resolution_m: number
  bbox: [number, number, number, number]
  query_coverage_ratio: number
  fully_covers_query: boolean
  stac_item_url: string
}

export interface PublicImagerySearchResponse {
  provider: string
  collection: string
  license_name: string
  license_url: string
  non_statutory_notice: string
  query_bbox: [number, number, number, number]
  coverage_basis: string
  total: number
  items: PublicImageryCandidate[]
}

export interface PublicImageryImportRequest {
  project_code: string
  task_code: string
  item_id: string
  bbox: [number, number, number, number]
  asset_code: string
  asset_name: string
  operator_code: string
}

export interface PublicImageryImportResponse {
  provider: string
  collection: string
  item_id: string
  source_product_id: string
  source_acquired_at: string
  source_cloud_cover: number | null
  source_wrs_path: number | null
  source_wrs_row: number | null
  query_coverage_ratio: number
  coverage_basis: string
  license_name: string
  non_statutory_notice: string
  asset: ImageryAssetItem
}

export interface PublicImageryBatchDraft {
  asset_code: string
  asset_name: string
}

export interface PublicImageryBatchImportItemRequest {
  item_id: string
  asset_code: string
  asset_name: string
}

export interface PublicImageryBatchImportRequest {
  project_code: string
  task_code: string
  operator_code: string
  batch_code: string
  comment: string
  bbox: [number, number, number, number]
  items: PublicImageryBatchImportItemRequest[]
}

export interface PublicImageryBatchSource {
  item_id: string
  asset_code: string
  source_product_id: string
  source_acquired_at: string
  source_cloud_cover: number | null
  source_wrs_path: number | null
  source_wrs_row: number | null
  subset_bbox: [number, number, number, number]
  query_coverage_ratio: number
}

export interface PublicImageryBatchImportResponse {
  provider: string
  collection: string
  license_name: string
  license_url: string
  non_statutory_notice: string
  query_bbox: [number, number, number, number]
  coverage_basis: string
  coverage_mode: 'single_scene_complete' | 'multi_scene_union'
  union_coverage_ratio: number
  union_covers_query: boolean
  sources: PublicImageryBatchSource[]
  batch: ImageryBatchResponse
}
