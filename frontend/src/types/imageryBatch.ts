import type { ImageryAssetItem } from '@/types/workbench'

export interface ImageryBatchManifestItem {
  filename: string
  asset_code: string
  asset_name: string
  sensor_type: string | null
  acquired_at: string | null
  cloud_cover: number | null
  processing_level: string | null
  data_status: 'operational' | 'demo'
}

export interface ImageryBatchManifest {
  batch_code: string
  operator_code: string
  comment: string
  items: ImageryBatchManifestItem[]
}

export interface ImageryBatchResponse {
  batch_code: string
  item_count: number
  total_size_bytes: number
  manifest_sha256: string
  imported_by: string
  imported_by_code: string
  imported_by_role: string
  comment: string
  created_at: string
  quality_recheck_required: boolean
  invalidated_task_count: number
  previous_quality_imagery_code: string | null
  current_quality_imagery_code: string | null
  items: ImageryAssetItem[]
}
