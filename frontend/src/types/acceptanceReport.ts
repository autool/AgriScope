import type { UserRoleCode } from '@/types/workbench'

export interface AcceptanceReportGeneratePayload {
  operator_code: string
  report_title: string
  comment: string
}

export interface AcceptanceReportFileEvidence {
  path: string
  format: 'DOCX' | 'PDF'
  file_size_bytes: number
  checksum_sha256: string
  page_count: number | null
}

export interface AcceptanceReport {
  report_code: string
  report_title: string
  version: number
  status: 'completed' | 'superseded' | 'invalid'
  delivery_package_code: string
  delivery_package_checksum_sha256: string
  task_plot_count: number
  task_updated_at_snapshot: string
  delivery_manifest_count: number
  bundle_size_bytes: number
  bundle_checksum_sha256: string
  files: AcceptanceReportFileEvidence[]
  generation_comment: string
  generated_by: string
  generated_by_code: string
  generated_by_role: UserRoleCode
  generated_at: string
  download_url: string | null
  is_current: boolean
  stale_reason: string | null
}

export interface AcceptanceReportList {
  task_code: string
  can_generate: boolean
  generate_blocker: string | null
  current_delivery_package_code: string | null
  items: AcceptanceReport[]
}
