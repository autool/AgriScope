export interface OfflineArchiveSourceSummary {
  source_kind: string
  source_count: number
  file_size_bytes: number
}

export interface OfflineArchiveVolume {
  sequence: number
  filename: string
  file_size_bytes: number
  checksum_sha256: string
  member_count: number
  source_size_bytes: number
  download_url: string | null
}

export interface OfflineArchive {
  archive_code: string
  archive_name: string
  version: number
  status: 'completed' | 'superseded' | 'invalid'
  volume_capacity_bytes: number
  volume_count: number
  source_count: number
  total_source_bytes: number
  total_archive_bytes: number
  source_snapshot_sha256: string
  manifest_size_bytes: number
  manifest_checksum_sha256: string
  delivery_package_code: string
  delivery_package_checksum_sha256: string
  generated_by: string
  generated_by_code: string
  generated_by_role: string
  generation_comment: string
  generated_at: string
  superseded_at: string | null
  is_current: boolean
  stale_reason: string | null
  manifest_download_url: string | null
  volumes: OfflineArchiveVolume[]
}

export interface OfflineArchiveOverview {
  task_code: string
  can_generate: boolean
  generate_blocker: string | null
  recommended_volume_capacity_bytes: number
  max_volume_capacity_bytes: number
  source_count: number
  total_source_bytes: number
  largest_source_bytes: number
  source_summaries: OfflineArchiveSourceSummary[]
  archives: OfflineArchive[]
}

export interface OfflineArchiveGeneratePayload {
  operator_code: string
  archive_name?: string | null
  volume_capacity_bytes?: number | null
  comment: string
}
