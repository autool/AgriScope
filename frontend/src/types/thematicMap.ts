export type ThematicSourceProductCode = 'true_color' | 'false_color' | 'ndvi'
export type ThematicOutputFormat = 'png' | 'pdf'

export interface ThematicMapTemplate {
  template_code: string
  template_name: string
  title_pattern: string
  producer: string
  page_width_px: number
  page_height_px: number
  dpi: number
  margin_px: number
  legend_position: 'bottom_right' | 'bottom_left'
  include_neatline: boolean
  include_north_arrow: boolean
  include_scale_bar: boolean
  created_by: string
  created_by_code: string
  created_by_role: string
  created_at: string
  updated_at: string
}

export interface ThematicMapSource {
  asset_code: string
  asset_name: string
  acquired_at: string
  data_status: 'operational' | 'demo'
  source_uri: string | null
  source_checksum_sha256: string | null
  available_products: ThematicSourceProductCode[]
  eligible: boolean
  unavailable_reason: string | null
}

export interface ThematicMapProduct {
  product_code: string
  template_code: string
  asset_code: string
  map_name: string
  map_number: string
  map_date: string
  source_product_code: ThematicSourceProductCode
  output_format: ThematicOutputFormat
  status: 'completed' | 'invalid'
  file_size_bytes: number
  checksum_sha256: string
  page_width_px: number
  page_height_px: number
  dpi: number
  source_uri: string
  source_checksum_sha256: string
  source_bounds_wgs84: number[]
  render_manifest: Record<string, unknown>
  generated_by: string
  generated_by_code: string
  generated_by_role: string
  generated_at: string
  download_url: string
  preview_url: string | null
}

export interface ThematicMapAtlasItem {
  sequence: number
  product_code: string
  map_name: string
  map_number: string
  map_date: string
  product_size_bytes: number
  product_checksum_sha256: string
  member_path: string
}

export interface ThematicMapAtlas {
  atlas_code: string
  atlas_name: string
  atlas_number: string
  version: number
  status: 'completed' | 'superseded' | 'invalid'
  package_size_bytes: number
  package_checksum_sha256: string
  pdf_filename: string
  pdf_size_bytes: number
  pdf_checksum_sha256: string
  pdf_page_count: number
  member_count: number
  product_count_snapshot: number
  product_latest_at_snapshot: string
  source_snapshot_sha256: string
  atlas_manifest: Record<string, unknown>
  generated_by: string
  generated_by_code: string
  generated_by_role: string
  generated_at: string
  superseded_at: string | null
  members: ThematicMapAtlasItem[]
  is_current: boolean
  stale_reason: string | null
  download_url: string | null
}

export interface ThematicMapOverview {
  project_code: string
  task_code: string
  template_count: number
  eligible_source_count: number
  product_count: number
  atlas_eligible_product_count: number
  atlas_count: number
  templates: ThematicMapTemplate[]
  sources: ThematicMapSource[]
  products: ThematicMapProduct[]
  atlases: ThematicMapAtlas[]
}

export interface ThematicMapTemplateCreatePayload {
  template_code: string
  template_name: string
  title_pattern: string
  producer: string
  page_width_px: number
  page_height_px: number
  dpi: number
  margin_px: number
  legend_position: 'bottom_right' | 'bottom_left'
  include_neatline: boolean
  include_north_arrow: boolean
  include_scale_bar: boolean
  operator_code: string
  comment: string
}

export interface ThematicMapGenerationItem {
  source_product_code: ThematicSourceProductCode
  output_format: ThematicOutputFormat
  map_name: string
  map_number: string
  map_date: string
}

export interface ThematicMapBatchGeneratePayload {
  template_code: string
  asset_code: string
  operator_code: string
  comment: string
  items: ThematicMapGenerationItem[]
}

export interface ThematicMapBatchGenerateResult {
  generated_count: number
  products: ThematicMapProduct[]
}

export interface ThematicMapAtlasGeneratePayload {
  atlas_name: string
  atlas_number: string
  product_codes: string[]
  operator_code: string
  comment: string
}

export interface ThematicMapAtlasGenerateResult {
  atlas: ThematicMapAtlas
}
