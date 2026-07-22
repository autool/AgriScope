export interface PlotAttributeWorkbookExportPayload {
  operator_code: string
  plot_codes?: string[] | null
}

export interface PlotAttributeImportBatch {
  batch_code: string
  task_code: string
  original_filename: string
  file_size_bytes: number
  checksum_sha256: string
  row_count: number
  changed_count: number
  unchanged_count: number
  updated_plot_codes: string[]
  imported_by: string
  imported_by_code: string
  imported_by_role: string
  import_comment: string
  imported_at: string
  quality_recheck_required: boolean
}

export interface PlotAttributeImportBatchList {
  task_code: string
  items: PlotAttributeImportBatch[]
}
