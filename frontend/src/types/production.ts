import type { UserRoleCode } from '@/types/workbench'

export type DatasetAssetType =
  | 'imagery'
  | 'vector'
  | 'table'
  | 'dem'
  | 'control'
  | 'weather'
  | 'management'
  | 'uav'
  | 'iot'

export type SecurityClassification = 'public' | 'internal' | 'restricted' | 'confidential'
export type ProductionDataStatus = 'operational' | 'demo'
export type ProductionBatchStatus =
  | 'draft'
  | 'planned'
  | 'in_progress'
  | 'reconciling'
  | 'completed'
  | 'cancelled'
export type WorkPackageStatus = 'pending' | 'in_progress' | 'blocked' | 'completed'
export type ReconciliationStatus = 'pending' | 'checking' | 'passed' | 'conflict'
export type PackageDeliveryStatus = 'pending' | 'submitted' | 'accepted' | 'returned'

export interface DatasetAsset {
  asset_code: string
  asset_name: string
  asset_type: DatasetAssetType
  source_name: string
  source_uri: string
  source_version: string
  checksum_sha256: string
  crs: string | null
  extent_bbox: [number, number, number, number] | null
  time_start: string | null
  time_end: string | null
  security_classification: SecurityClassification
  data_status: ProductionDataStatus
  verification_status: string
  physical_file_uri: string | null
  physical_original_filename: string | null
  physical_file_size_bytes: number | null
  physical_checksum_sha256: string | null
  physical_media_type: string | null
  verified_at: string | null
  verified_by: string | null
  verified_by_code: string | null
  verified_by_role: UserRoleCode | 'independent_supervisor' | null
  verification_comment: string | null
  parent_asset_codes: string[]
  metadata: Record<string, unknown>
  registered_by: string
  registered_by_code: string
  registered_by_role: UserRoleCode | 'independent_supervisor'
  created_at: string
}

export interface DatasetAssetMetadataPayload {
  asset_code: string
  asset_name: string
  asset_type: DatasetAssetType
  source_name: string
  source_uri: string
  source_version: string
  crs: string | null
  extent_bbox: [number, number, number, number] | null
  time_start: string | null
  time_end: string | null
  security_classification: SecurityClassification
  data_status: ProductionDataStatus
  parent_asset_codes: string[]
  lineage_relation_type: string
  process_code: string | null
  metadata: Record<string, unknown>
  operator_code: string
}

export interface DatasetAssetCreatePayload extends DatasetAssetMetadataPayload {
  checksum_sha256: string
}

export interface DatasetAssetUploadPayload extends DatasetAssetMetadataPayload {
  verification_comment: string
}

export interface DatasetAssetVerificationResult {
  verification_code: string
  verification_status: 'verified' | 'rejected'
  checksum_match: boolean
  expected_checksum_sha256: string
  computed_checksum_sha256: string
  file_size_bytes: number
  media_type: string
  verification_error: string | null
  created_at: string
  asset: DatasetAsset
}

export type DatasetAssetBatchItemPayload = Omit<
  DatasetAssetMetadataPayload,
  'operator_code'
> & {
  filename: string
}

export interface DatasetAssetBatchCreatePayload {
  batch_code: string
  operator_code: string
  comment: string
  items: DatasetAssetBatchItemPayload[]
}

export interface DatasetAssetImportBatchSummary {
  batch_code: string
  item_count: number
  total_size_bytes: number
  manifest_sha256: string
  imported_by: string
  imported_by_code: string
  imported_by_role: UserRoleCode | 'independent_supervisor'
  comment: string
  created_at: string
}

export interface DatasetAssetBatchResult extends DatasetAssetImportBatchSummary {
  items: DatasetAsset[]
}

export interface WorkArea {
  city_code: string
  city_name: string
  region_code: string
  region_name: string
  plot_count: number
  area_ha: number
  assigned_batch_codes: string[]
}

export interface WorkPackage {
  package_code: string
  package_name: string
  region_code: string
  region_name: string
  region_level: string
  planned_area_ha: number
  planned_plot_count: number
  active_plot_count: number
  completed_plot_count: number
  progress: number
  assignee_code: string
  assignee_name: string
  deadline: string
  overdue: boolean
  status: WorkPackageStatus
  reconciliation_status: ReconciliationStatus
  delivery_status: PackageDeliveryStatus
  updated_at: string
}

export interface ProductionBatch {
  batch_code: string
  batch_name: string
  source_asset_code: string | null
  target_asset_code: string | null
  rule_config_version: number
  rule_profile_snapshot: Record<string, unknown>
  planned_start_date: string
  planned_end_date: string
  status: ProductionBatchStatus
  package_count: number
  planned_plot_count: number
  completed_plot_count: number
  progress: number
  created_by: string
  created_by_code: string
  created_at: string
  packages: WorkPackage[]
}

export interface ProductionOverview {
  project_code: string
  task_code: string
  metrics: {
    asset_count: number
    pending_asset_verification_count: number
    dataset_import_batch_count: number
    batch_count: number
    active_batch_count: number
    package_count: number
    overdue_package_count: number
    assigned_plot_count: number
    completed_plot_count: number
  }
  asset_type_counts: Record<string, number>
  assets: DatasetAsset[]
  dataset_import_batches: DatasetAssetImportBatchSummary[]
  work_areas: WorkArea[]
  batches: ProductionBatch[]
}

export interface ProductionBatchCreatePayload {
  batch_code: string
  batch_name: string
  source_asset_code: string | null
  target_asset_code: string | null
  planned_start_date: string
  planned_end_date: string
  operator_code: string
}

export interface WorkPackageCreatePayload {
  region_codes: string[]
  assignee_code: string
  deadline: string
  operator_code: string
}

export interface WorkPackageCreateResult {
  batch_code: string
  created_count: number
  assigned_plot_count: number
  packages: WorkPackage[]
}

export interface WorkPackageUpdatePayload {
  assignee_code?: string
  deadline?: string
  status?: WorkPackageStatus
  reconciliation_status?: ReconciliationStatus
  delivery_status?: PackageDeliveryStatus
  operator_code: string
}
