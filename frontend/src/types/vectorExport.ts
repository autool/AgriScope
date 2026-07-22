import type { UserRoleCode } from '@/types/workbench'

export type VectorExportFormat = 'geojson' | 'shapefile' | 'kml' | 'filegdb'
export type VectorLandClass = '耕地' | '园地' | '林地' | '草地' | '水域' | '建设用地'

export interface VectorExportGeneratePayload {
  operator_code: string
  export_title: string
  formats: VectorExportFormat[]
  district_codes: string[]
  land_classes: VectorLandClass[]
  comment: string
}

export interface VectorExportManifestFile {
  path: string
  format: string
  file_size_bytes: number
  checksum_sha256: string
}

export interface VectorExportPackage {
  export_code: string
  export_title: string
  version: number
  status: 'completed' | 'superseded' | 'invalid'
  formats: VectorExportFormat[]
  district_codes: string[]
  land_classes: VectorLandClass[]
  feature_count: number
  task_plot_count: number
  task_updated_at_snapshot: string
  file_size_bytes: number
  checksum_sha256: string
  files: VectorExportManifestFile[]
  generation_comment: string
  generated_by: string
  generated_by_code: string
  generated_by_role: UserRoleCode
  generated_at: string
  download_url: string | null
  is_current: boolean
  stale_reason: string | null
}

export interface VectorExportList {
  task_code: string
  items: VectorExportPackage[]
}

export interface VectorExportFilterOption {
  code: string | null
  label: string
  parent_label: string | null
  feature_count: number
}

export interface VectorExportOptions {
  task_code: string
  total_feature_count: number
  max_feature_count: number
  supported_formats: VectorExportFormat[]
  districts: VectorExportFilterOption[]
  land_classes: VectorExportFilterOption[]
}
