export interface GeoJsonGeometry {
  type: string
  coordinates: unknown
}

export interface GeoJsonFeature<TProperties = Record<string, unknown>> {
  type: 'Feature'
  geometry: GeoJsonGeometry
  properties: TProperties
}

export interface GeoJsonFeatureCollection<TProperties = Record<string, unknown>> {
  type: 'FeatureCollection'
  features: Array<GeoJsonFeature<TProperties>>
}

export interface BoundaryProperties extends Record<string, unknown> {
  boundary_code: string
  boundary_name: string
  boundary_level: 'province' | 'city' | 'district' | 'township'
  parent_code: string | null
  source_name: string
  source_uri: string | null
  source_version: string | null
  source_updated_at: string | null
}

export interface ProjectSummary {
  project_code: string
  project_name: string
  province: string
  monitor_year: number
  status: string
  progress: number
  deadline: string | null
}

export interface TaskSummary {
  task_code: string
  task_name: string
  administrative_region: string
  assignee: string | null
  status: string
  total_plots: number
  completed_plots: number
  quality_score: number | null
  deadline: string | null
}

export interface ImagerySummary {
  asset_code: string
  asset_name: string
  sensor_type: string
  acquired_at: string
  cloud_cover: number | null
  resolution_m: number | null
  processing_level: string | null
  calibration_status: string
  correction_status: string
}

export interface WorkbenchOverview {
  project: ProjectSummary
  task: TaskSummary
  imagery: ImagerySummary | null
  statistics: {
    plot_count: number
    interpreted_count: number
    open_issue_count: number
    review_record_count: number
    current_cycle_review_count: number
    operational_imagery_count: number
    pending_disaster_count: number
    pending_field_verification_count: number
  }
  workflow: {
    progress: number
    current_stage: string
    stages: Array<{
      code: 'imagery' | 'interpretation' | 'quality' | 'field' | 'review' | 'delivery'
      label: string
      status: 'pending' | 'active' | 'blocked' | 'completed'
      progress: number
      detail: string
    }>
  }
  reviews: Array<{
    review_level: string
    action: string
    reviewer: string
    reviewer_code: string | null
    reviewer_role: string | null
    comment: string | null
    created_at: string
  }>
}

export type UserRoleCode =
  | 'interpreter'
  | 'field_inspector'
  | 'quality_inspector'
  | 'project_manager'
  | 'client_reviewer'
  | 'independent_supervisor'

export interface ProjectUser {
  user_code: string
  display_name: string
  role_code: UserRoleCode
  role_name: string
  status: 'active' | 'disabled'
  is_default: boolean
  capabilities: string[]
}

export interface ProjectUserList {
  project_code: string
  users: ProjectUser[]
}

export interface ReviewActionPayload {
  action: 'pass' | 'return' | 'reject'
  reviewer_code: string
  comment?: string | null
  issue_type?: string | null
}

export interface ReviewActionResult {
  task: TaskSummary
  previous_status: string
  current_status: string
  action: 'pass' | 'return' | 'reject'
  record_id: number
  reviewer_code: string
  reviewer_name: string
  reviewer_role: UserRoleCode
}

export interface PlotRollbackPayload {
  target_version: number
  operator_code: string
  comment?: string | null
}

export interface AreaGroupItem {
  label: string
  code: string | null
  parent_label: string | null
  plot_count: number
  area_ha: number
  area_mu: number
  percentage: number
}

export interface AreaStatistics {
  task_code: string
  monitor_year: number
  generated_at: string
  total_plot_count: number
  total_area_ha: number
  total_area_mu: number
  average_plot_area_ha: number
  farmland_area_ha: number
  crop_assigned_plot_count: number
  crop_assignment_rate: number
  by_land_class: AreaGroupItem[]
  by_crop_type: AreaGroupItem[]
  by_planting_mode: AreaGroupItem[]
  by_city: AreaGroupItem[]
  by_district: AreaGroupItem[]
  by_village: AreaGroupItem[]
  annual_trend: Array<{
    year: number
    area_ha: number
    year_over_year: number | null
    source_name: string
    source_version: string | null
    recorded_at: string
    is_current: boolean
  }>
}

export interface AreaStatisticsHistoryImportMetadata {
  source_name: string
  source_uri: string
  source_version: string
  operator_code: string
  comment: string
  conflict_strategy: 'reject' | 'replace'
}

export interface AreaStatisticsHistoryImportResult {
  task_code: string
  batch_code: string
  imported_count: number
  replaced_count: number
  years: number[]
  source_checksum_sha256: string
  imported_by: string
  imported_by_code: string
  imported_by_role: UserRoleCode
  imported_at: string
}

export interface StatisticsReportGeneratePayload {
  operator_code: string
  report_title: string
  comment: string
}

export interface StatisticsReport {
  report_code: string
  report_title: string
  version: number
  status: 'completed' | 'superseded' | 'invalid'
  bundle_size_bytes: number
  bundle_checksum_sha256: string
  xlsx_size_bytes: number
  xlsx_checksum_sha256: string
  pdf_size_bytes: number
  pdf_checksum_sha256: string
  task_plot_count: number
  task_updated_at_snapshot: string
  history_snapshot_count: number
  history_latest_updated_at: string | null
  report_manifest: Record<string, unknown>
  generation_comment: string
  generated_by: string
  generated_by_code: string
  generated_by_role: UserRoleCode
  generated_at: string
  download_url: string | null
  is_current: boolean
  stale_reason: string | null
}

export interface StatisticsReportList {
  task_code: string
  items: StatisticsReport[]
}

export interface ImageryProcessingStep {
  step_code: string
  step_name: string
  sequence: number
  is_required: boolean
  status: string
  progress: number
  parameters: Record<string, unknown>
  output_uri: string | null
  output_verified: boolean
  output_size_bytes: number | null
  output_checksum_sha256: string | null
  processor_name: string | null
  processor_version: string | null
  artifact_error: string | null
  started_at: string | null
  completed_at: string | null
}

export interface ImageryArtifactRegisterPayload {
  operator_code: string
  output_relative_path: string
  processor_name: string
  processor_version: string
  comment?: string | null
}

export interface ImageryGcpControlPointDraft {
  point_id: string
  pixel_column: number | null
  pixel_row: number | null
  x: number | null
  y: number | null
  z: number | null
  source: string
}

export interface ImageryStepExecutePayload {
  operator_code: string
  parameters: Record<string, unknown>
  comment?: string | null
}

export interface ImagerySourceLevelAcceptPayload {
  operator_code: string
  expected_processing_level: 'L2A' | 'L2'
  confirm_no_algorithm_execution: true
  justification: string
}

export interface ImageryProcessing {
  asset_code: string
  asset_name: string
  sensor_type: string
  acquired_at: string
  cloud_cover: number | null
  resolution_m: number | null
  processing_level: string | null
  completion_rate: number
  completed_steps: number
  total_steps: number
  steps: ImageryProcessingStep[]
}

export type ImageryQuicklookProductCode = 'source' | 'true_color' | 'false_color' | 'ndvi'

export interface ImageryQuicklookProduct {
  product_code: ImageryQuicklookProductCode
  product_name: string
  available: boolean
  unavailable_reason: string | null
  source_kind: 'source_asset' | 'verified_band_products' | null
  source_uri: string | null
  source_checksum_sha256: string | null
  preview_url: string | null
  preview_checksum_sha256: string | null
  bounds_wgs84: [number, number, number, number] | null
  width: number | null
  height: number | null
  band_indexes: number[]
  band_descriptions: string[]
  stretch_ranges: Array<[number, number]>
  value_range: [number, number] | null
  renderer_version: string | null
  generated_at: string | null
}

export interface ImageryQuicklook {
  asset_code: string
  asset_name: string
  data_status: 'operational' | 'demo'
  products: ImageryQuicklookProduct[]
}

export interface ImageryBusinessMetadataField {
  value: string | number | null
  source: string
  raster_tag: string | null
  raster_value: string | number | null
  raster_raw_value: string | null
  user_value: string | number | null
  precision: string | null
  timezone_assumption: string | null
}

export interface ImageryRasterMetadata extends Record<string, unknown> {
  descriptions?: Array<string | null>
  has_rpc?: boolean
  rpc_summary?: Record<string, number | null> | null
  import_batch_code?: string
  import_manifest_sha256?: string
  business_metadata?: Partial<Record<
    'sensor_type' | 'acquired_at' | 'processing_level' | 'cloud_cover',
    ImageryBusinessMetadataField
  >>
}

export interface ImageryAssetItem {
  asset_code: string
  asset_name: string
  sensor_type: string
  acquired_at: string
  cloud_cover: number | null
  resolution_m: number | null
  processing_level: string | null
  data_status: 'operational' | 'demo'
  calibration_status: string
  correction_status: string
  original_filename: string | null
  file_uri: string | null
  file_format: string | null
  file_size_bytes: number | null
  checksum_sha256: string | null
  band_count: number | null
  raster_width: number | null
  raster_height: number | null
  crs: string | null
  raster_metadata: ImageryRasterMetadata
  imported_by: string | null
  footprint: GeoJsonGeometry | null
  file_verified: boolean
  file_error: string | null
  created_at: string
}

export interface ImageryAssetCatalog {
  project_code: string
  total: number
  available: number
  metadata_only: number
  items: ImageryAssetItem[]
}

export interface DeliveryManifestItem {
  path: string
  category: string
  format: string
  record_count: number | null
  description: string
  file_size_bytes?: number | null
  checksum_sha256?: string | null
  source_entity_code?: string | null
  source_uri?: string | null
  evidence_status?: 'included' | 'referenced' | 'not_provided' | 'legacy'
}

export interface DeliveryPackage {
  package_code: string
  package_name: string
  version: number
  status: string
  generated_by: string
  generated_by_code: string | null
  generated_by_role: UserRoleCode | null
  file_size_bytes: number | null
  checksum_sha256: string | null
  manifest: DeliveryManifestItem[]
  quality_summary: Record<string, number | string | boolean | null>
  completed_at: string | null
  download_url: string | null
  is_current: boolean
  stale_reason: string | null
}

export interface DeliveryGeneratePayload {
  operator_code: string
  package_name?: string | null
}

export interface DeliveryList {
  task_code: string
  can_generate: boolean
  generate_blocker: string | null
  packages: DeliveryPackage[]
}

export interface PlotAttributes {
  plot_code: string
  owner_village: string | null
  area_ha: number | null
  land_class: string | null
  crop_type: string | null
  planting_mode: string | null
  irrigation_condition: string | null
  custom_attributes: CustomAttributeValues
  source_name: string | null
  source_feature_id: string | null
  source_uri: string | null
  source_version: string | null
  source_updated_at: string | null
  province_name: string | null
  city_name: string | null
  district_name: string | null
  district_code: string | null
  interpretation_status: string
  version: number
  updated_at?: string
}

export interface PlotAttributeUpdate {
  land_class: string
  crop_type: string | null
  planting_mode: string | null
  irrigation_condition: string | null
  custom_attributes: CustomAttributeValues
}

export interface PlotAttributeMutationPayload extends PlotAttributeUpdate {
  operator_code: string
  comment?: string | null
}

export interface PolygonGeometry {
  type: 'Polygon'
  coordinates: Array<Array<[number, number]>>
}

export interface LineStringGeometry {
  type: 'LineString'
  coordinates: Array<[number, number]>
}

export interface PlotCreatePayload extends PlotAttributeUpdate {
  plot_code?: string | null
  owner_village: string
  geometry: PolygonGeometry
  operator_code: string
  comment?: string | null
}

export type PlotCreateDraftPayload = Omit<PlotCreatePayload, 'operator_code'>

export interface PlotGeometryUpdatePayload {
  geometry: PolygonGeometry
  operator_code: string
  comment?: string | null
}

export interface PlotDeletePayload {
  operator_code: string
  comment: string
}

export interface PlotSplitPayload {
  cutter: LineStringGeometry
  operator_code: string
  comment: string
}

export interface PlotSplitResult {
  operation_code: string
  task_code: string
  source_plot_code: string
  result_plots: PlotAttributes[]
  source_area_ha: number
  result_area_ha: number
  area_difference_ha: number
  total_plot_count: number
  completed_plot_count: number
  quality_recheck_required: boolean
}

export interface PlotMergePayload extends PlotAttributeUpdate {
  plot_codes: string[]
  owner_village: string
  operator_code: string
  comment: string
}

export type PlotMergeDraftPayload = Omit<PlotMergePayload, 'operator_code'>

export interface PlotMergeResult {
  operation_code: string
  task_code: string
  source_plot_codes: string[]
  result_plot: PlotAttributes
  source_area_ha: number
  result_area_ha: number
  area_difference_ha: number
  total_plot_count: number
  completed_plot_count: number
  quality_recheck_required: boolean
}

export interface PlotOperationSummary {
  operation_code: string
  operation_type: 'split' | 'merge'
  source_plot_codes: string[]
  result_plot_codes: string[]
}

export interface PlotOperationHistoryState {
  can_undo: boolean
  can_redo: boolean
  undo_operation: PlotOperationSummary | null
  redo_operation: PlotOperationSummary | null
}

export interface PlotHistoryActionPayload {
  operator_code: string
  comment: string
}

export interface PlotHistoryActionResult {
  action: 'undo' | 'redo'
  operation: PlotOperationSummary
  active_plot_codes: string[]
  inactive_plot_codes: string[]
  total_plot_count: number
  completed_plot_count: number
  quality_recheck_required: boolean
}

export interface BatchPlotAttributeUpdatePayload {
  plot_codes: string[]
  attributes: PlotAttributeUpdate
  operator_code: string
  comment?: string | null
}

export type BatchPlotAttributeUpdateDraft = Omit<
  BatchPlotAttributeUpdatePayload,
  'operator_code'
>

export interface BatchPlotAttributeUpdateResult {
  task_code: string
  updated_count: number
  updated_plot_codes: string[]
  total_plot_count: number
  completed_plot_count: number
  quality_recheck_required: boolean
}

export interface QualityRuleResult {
  rule_code: string
  label: string
  status: 'pass' | 'warning' | 'fail'
  severity: 'low' | 'medium' | 'high'
  detail: string
  blocking: boolean
}

export interface QualityCheckResult {
  plot_code: string
  score: number
  can_submit: boolean
  checked_plot_count: number
  total_plot_count: number
  passing_plot_count: number
  rules: QualityRuleResult[]
}

export interface TaskQualityCheckPayload {
  operator_code: string
  comment?: string | null
}

export interface PlotQualityCheckPayload {
  operator_code: string
}

export interface QualityRuleSummary {
  rule_code: string
  label: string
  pass_count: number
  warning_count: number
  fail_count: number
  blocking_issue_count: number
}

export interface TaskQualityCheckResult {
  run_code: string
  task_code: string
  total_plot_count: number
  checked_plot_count: number
  passing_plot_count: number
  failed_plot_count: number
  average_score: number | null
  issue_count: number
  can_submit: boolean
  duration_ms: number
  executed_at: string
  rule_config_version: number
  custom_field_schema_digest: string
  rule_summaries: QualityRuleSummary[]
}

export interface TaskQualityRun {
  run_code: string
  task_code: string
  task_plot_count: number
  task_updated_at_snapshot: string
  rule_config_version: number
  rule_config_snapshot: Record<string, unknown>
  custom_field_schema_digest: string
  custom_field_snapshot: Array<Record<string, unknown>>
  checked_plot_count: number
  passing_plot_count: number
  failed_plot_count: number
  average_score: number | null
  issue_count: number
  can_submit: boolean
  duration_ms: number
  rule_summaries: QualityRuleSummary[]
  operator: string
  operator_code: string
  operator_role: string
  comment: string | null
  created_at: string
}

export interface TaskQualityRunList {
  task_code: string
  total_count: number
  items: TaskQualityRun[]
}

export interface QualityIssueItem {
  id: number
  plot_code: string | null
  rule_code: string
  rule_label: string
  issue_type: string
  severity: 'high' | 'medium' | 'low'
  description: string
  status: 'open' | 'resolved' | string
  source: string
  assignee: string | null
  resolved_by: string | null
  resolved_by_code: string | null
  resolved_by_role: string | null
  resolution_comment: string | null
  created_at: string
  resolved_at: string | null
  plot_version: number | null
  city_name: string | null
  district_name: string | null
  owner_village: string | null
  land_class: string | null
  crop_type: string | null
  area_ha: number | null
}

export interface QualityIssueResolvePayload {
  operator_code: string
  comment: string
}

export interface QualityIssueResolveResult {
  issue_id: number
  status: 'resolved'
  resolved_by: string
  resolved_by_code: string
  resolved_by_role: UserRoleCode
  resolution_comment: string
  resolved_at: string
}

export interface QualityIssueRuleCount {
  rule_code: string
  rule_label: string
  total_count: number
  open_count: number
}

export interface QualityIssueList {
  task_code: string
  page: number
  page_size: number
  total_count: number
  open_count: number
  resolved_count: number
  high_count: number
  medium_count: number
  low_count: number
  rule_counts: QualityIssueRuleCount[]
  items: QualityIssueItem[]
}

export interface QualityIssueQuery {
  status: 'open' | 'resolved' | 'all'
  rule_code?: string
  severity?: 'high' | 'medium' | 'low'
  issue_type?: string
  keyword?: string
  page: number
  page_size: number
}

export interface TaskSubmitPayload {
  reviewer_code: string
  comment?: string | null
}

export interface PlotProperties extends Record<string, unknown> {
  plot_code: string
  owner_village?: string | null
  area_ha?: number | null
  land_class?: string | null
  custom_attributes?: CustomAttributeValues
  source_name?: string | null
  source_feature_id?: string | null
  source_uri?: string | null
  source_version?: string | null
  source_updated_at?: string | null
  province_name?: string | null
  city_name?: string | null
  district_name?: string | null
  district_code?: string | null
}

export interface BoundingBox {
  min_lon: number
  min_lat: number
  max_lon: number
  max_lat: number
}

export interface PlotCatalogItem {
  plot_code: string
  source_feature_id: string | null
  land_class: string | null
  extent: [number, number, number, number]
}

export interface PlotCatalogDistrict {
  district_code: string
  plot_count: number
  plots: PlotCatalogItem[]
}

export interface PlotCatalog {
  task_code: string
  total_count: number
  land_class_counts: Record<string, number>
  districts: PlotCatalogDistrict[]
}

export interface PlotViewportRequest extends BoundingBox {
  task_code: string
  max_features: number
}

export interface PlotViewportResponse extends GeoJsonFeatureCollection<PlotProperties> {
  matched_count: number
  max_features: number
  requires_zoom: boolean
}

export interface FieldVerificationItem extends Record<string, unknown> {
  verification_code: string
  investigator: string
  investigator_code: string | null
  lon: number
  lat: number
  location_accuracy_m: number | null
  observed_land_class: string | null
  observed_crop_type: string | null
  photo_urls: string[]
  voice_url: string | null
  remark: string | null
  captured_at: string
  source_name: string | null
  source_uri: string | null
  source_version: string | null
  source_record_id: string | null
  source_checksum_sha256: string | null
  source_file_uri: string | null
  source_file_size_bytes: number | null
  import_batch_code: string | null
  imported_by: string | null
  imported_by_code: string | null
  imported_by_role: UserRoleCode | null
  matched_plot_code: string | null
  offset_distance_m: number | null
  match_status: string
  resolution_status: string
  resolution_decision: string | null
  resolution_comment: string | null
  resolved_by: string | null
  resolved_by_code: string | null
  resolved_by_role: UserRoleCode | null
  verified_artifact_count: number
  artifacts: FieldVerificationArtifact[]
}

export type FieldVerificationArtifactType = 'photo' | 'voice' | 'form'

export interface FieldVerificationArtifact {
  artifact_code: string
  artifact_type: FieldVerificationArtifactType
  original_filename: string
  media_type: string
  file_size_bytes: number
  checksum_sha256: string
  description: string
  uploaded_by: string
  uploaded_by_code: string
  uploaded_by_role: UserRoleCode
  created_at: string
  download_url: string
}

export interface FieldVerificationArtifactUploadPayload {
  artifact_type: FieldVerificationArtifactType
  uploader_code: string
  comment: string
  file: File
}

export interface FieldVerificationImportItem {
  verification_code: string
  source_record_id: string
  lon: number
  lat: number
  observed_land_class: string | null
  observed_crop_type: string | null
  photo_urls: string[]
  voice_url: string | null
  remark: string | null
  captured_at: string
}

export interface FieldVerificationBatchImportPayload {
  source_name: string
  source_uri: string
  source_version: string
  uploader_code: string
  comment: string
  records: FieldVerificationImportItem[]
}

export interface FieldVerificationFileImportMetadata {
  source_name: string
  source_uri: string
  source_version: string
  uploader_code: string
  comment: string
}

export interface FieldVerificationBatchImportResult {
  task_code: string
  batch_code: string
  imported_count: number
  consistent_count: number
  offset_count: number
  unmatched_count: number
  time_mismatch_count: number
  issue_count: number
  source_checksum_sha256: string
  imported_by: string
  imported_by_code: string
  imported_by_role: UserRoleCode
  imported_at: string
}

export interface FieldRematchPayload {
  operator_code: string
}

export type FieldResolutionDecision =
  | 'keep_internal'
  | 'use_field'
  | 'compromise'
  | 'reject_field'

export interface FieldResolutionPayload {
  decision: FieldResolutionDecision
  reviewer_code: string
  comment: string
  target_land_class?: string | null
  target_crop_type?: string | null
}

export interface FieldReopenPayload {
  operator_code: string
  comment: string
}

export interface FieldVerificationList {
  total: number
  consistent: number
  offset: number
  unmatched: number
  time_mismatch: number
  pending_resolution: number
  items: FieldVerificationItem[]
}

export interface RuleConfig {
  project_code: string
  field_offset_threshold_m: number
  field_search_radius_m: number
  positional_accuracy_pixels: number
  max_capture_image_days: number
  construction_min_area_sqm: number
  other_agricultural_min_area_sqm: number
  completeness_rate_min: number
  boundary_agreement_rate_min: number
  land_class_accuracy_min: number
  key_field_accuracy_min: number
  max_cloud_cover_percent: number | null
  output_crs: string
  output_projection: string
  version: number
  updated_by: string
  updated_by_code: string | null
  updated_by_role: UserRoleCode | null
  updated_at: string
}

export interface RuleConfigUpdatePayload {
  field_offset_threshold_m: number
  field_search_radius_m: number
  positional_accuracy_pixels: number
  max_capture_image_days: number
  construction_min_area_sqm: number
  other_agricultural_min_area_sqm: number
  completeness_rate_min: number
  boundary_agreement_rate_min: number
  land_class_accuracy_min: number
  key_field_accuracy_min: number
  max_cloud_cover_percent: number | null
  output_crs: string
  output_projection: string
  operator_code: string
}

export interface DisasterPatch extends Record<string, unknown> {
  patch_code: string
  disaster_type: string
  severity: '轻度' | '中度' | '重度' | '绝收'
  status: 'pending' | 'confirmed' | 'excluded'
  affected_area_ha: number
  crop_type: string | null
  detected_at: string
  ndvi_change: number | null
  source: string
  source_uri: string | null
  source_version: string | null
  source_feature_id: string | null
  source_checksum_sha256: string | null
  import_batch_code: string | null
  imported_by: string | null
  imported_by_code: string | null
  imported_by_role: UserRoleCode | null
  reviewed_by: string | null
  reviewed_by_code: string | null
  reviewed_by_role: UserRoleCode | null
  review_comment: string | null
  reviewed_at: string | null
}

export interface DisasterImportProperties extends Record<string, unknown> {
  patch_code: string
  source_feature_id: string
  disaster_type: '洪涝' | '干旱' | '冻害' | '病虫害' | '风雹' | '其他'
  severity: '轻度' | '中度' | '重度' | '绝收'
  crop_type?: string | null
  detected_at: string
  ndvi_change?: number | null
}

export interface DisasterGeoJsonImportPayload {
  type: 'FeatureCollection'
  source_name: string
  source_uri: string
  source_version: string
  operator_code: string
  conflict_policy: 'reject' | 'replace'
  comment: string
  features: Array<GeoJsonFeature<DisasterImportProperties>>
}

export interface DisasterGeoJsonImportResult {
  task_code: string
  batch_code: string
  imported_count: number
  created_count: number
  replaced_count: number
  patch_codes: string[]
  source_checksum_sha256: string
  imported_by: string
  imported_by_code: string
  imported_by_role: UserRoleCode
  imported_at: string
}

export interface DisasterPatchUpdatePayload {
  severity: '轻度' | '中度' | '重度' | '绝收'
  status: 'pending' | 'confirmed' | 'excluded'
  reviewer_code: string
  comment?: string | null
}

export interface DisasterSummary {
  task_code: string
  generated_at: string
  total_patches: number
  affected_area_ha: number
  pending_count: number
  confirmed_count: number
  by_severity: Array<{ label: string; patch_count: number; area_ha: number; percentage: number }>
  by_type: Array<{ label: string; patch_count: number; area_ha: number; percentage: number }>
  items: DisasterPatch[]
  feature_collection: GeoJsonFeatureCollection
}

export interface DisasterReportGeneratePayload {
  operator_code: string
  report_title: string
  comment: string
}

export interface DisasterReport {
  report_code: string
  report_title: string
  status: 'completed' | 'superseded' | 'invalid'
  file_size_bytes: number
  checksum_sha256: string
  source_patch_count: number
  source_confirmed_count: number
  source_excluded_count: number
  source_latest_updated_at: string
  affected_area_ha: number
  report_manifest: Record<string, unknown>
  generation_comment: string
  generated_by: string
  generated_by_code: string
  generated_by_role: UserRoleCode
  generated_at: string
  download_url: string | null
  is_current: boolean
}

export interface DisasterReportList {
  task_code: string
  items: DisasterReport[]
}

export interface PlotVersionList {
  plot_code: string
  current_version: number
  versions: Array<Record<string, unknown> & {
    version: number
    change_summary?: string | null
  }>
}
import type { CustomAttributeValues } from '@/types/plotAttributeField'
