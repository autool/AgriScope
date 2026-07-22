export type StationType = 'weather' | 'soil' | 'crop' | 'pest' | 'comprehensive'
export type DeviceType =
  | 'weather_sensor'
  | 'soil_sensor'
  | 'camera'
  | 'insect_trap'
  | 'spore_trap'
  | 'gateway'
  | 'other'
export type DeviceStatus = 'online' | 'offline' | 'abnormal' | 'maintenance' | 'retired'
export type FaultSeverity = 'minor' | 'major' | 'critical'
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

export interface MonitoringStation {
  station_code: string
  station_name: string
  province_code: string
  province_name: string
  city_code: string
  city_name: string
  district_code: string
  district_name: string
  longitude: number
  latitude: number
  station_type: StationType
  owner_department: string
  source_name: string
  source_uri: string
  source_version: string
  evidence_uri: string
  evidence_size_bytes: number
  evidence_sha256: string
  status: string
  registered_by: string
  registered_by_code: string
  registered_by_role: string
  created_at: string
}

export interface MonitoringDevice {
  station_code: string
  device_code: string
  device_name: string
  device_type: DeviceType
  vendor: string
  model_number: string
  serial_number: string
  owner_department: string
  installed_at: string
  photo_uri: string
  photo_size_bytes: number
  photo_sha256: string
  status: DeviceStatus
  last_telemetry_at: string | null
  registered_by: string
  registered_by_code: string
  registered_by_role: string
  created_at: string
}

export interface DeviceTelemetry {
  device_code: string
  idempotency_key: string
  observed_at: string
  metric_code: string
  metric_value: number | null
  metric_unit: string | null
  payload: Record<string, unknown>
  evidence_uri: string | null
  evidence_size_bytes: number | null
  evidence_sha256: string | null
  ingested_by: string
  ingested_by_code: string
  ingested_by_role: string
  received_at: string
}

export interface DeviceFault {
  device_code: string
  fault_code: string
  severity: FaultSeverity
  reason: string
  occurred_at: string
  status: 'open' | 'resolved'
  reported_by: string
  reported_by_code: string
  reported_by_role: string
  resolution_comment: string | null
  resolution_evidence_uri: string | null
  resolved_by: string | null
  resolved_by_code: string | null
  resolved_by_role: string | null
  resolved_at: string | null
  created_at: string
}

export interface PestModelVersion {
  model_code: string
  model_version: string
  model_name: string
  target_type: 'pest' | 'disease'
  deployment_target: string
  training_source_uri: string
  evaluation_source_uri: string
  artifact_uri: string
  artifact_size_bytes: number
  artifact_sha256: string
  accuracy: number
  recall: number
  f1_score: number
  roc_auc: number
  status: 'active' | 'superseded'
  superseded_by_version: string | null
  registered_by: string
  registered_by_code: string
  registered_by_role: string
  created_at: string
}

export interface PestAssessment {
  assessment_code: string
  device_code: string | null
  model_code: string
  model_version: string
  observed_at: string
  input_uri: string
  input_size_bytes: number
  input_sha256: string
  input_summary: Record<string, unknown>
  target_name: string
  prediction_label: string
  confidence: number
  prediction_basis: string
  status: 'pending_review' | 'approved' | 'rejected'
  submitted_by: string
  submitted_by_code: string
  submitted_by_role: string
  review_comment: string | null
  reviewed_by: string | null
  reviewed_by_code: string | null
  reviewed_by_role: string | null
  reviewed_at: string | null
  created_at: string
}

export interface PestAlert {
  alert_code: string
  assessment_code: string
  risk_level: RiskLevel
  message: string
  channels: string[]
  recipients: string[]
  status: 'pending' | 'delivered'
  created_by: string
  created_by_code: string
  created_by_role: string
  delivery_receipt_uri: string | null
  delivery_receipt_size_bytes: number | null
  delivery_receipt_sha256: string | null
  delivered_by: string | null
  delivered_by_code: string | null
  delivered_by_role: string | null
  delivered_at: string | null
  created_at: string
}

export interface MonitoringEvent {
  entity_type: string
  entity_code: string
  event_type: string
  detail: Record<string, unknown>
  actor: string
  actor_code: string
  actor_role: string
  created_at: string
}

export interface MonitoringOverview {
  station_count: number
  device_count: number
  online_device_count: number
  abnormal_device_count: number
  telemetry_count: number
  open_fault_count: number
  active_model_count: number
  pending_assessment_count: number
  pending_alert_count: number
  stations: MonitoringStation[]
  devices: MonitoringDevice[]
  telemetry: DeviceTelemetry[]
  faults: DeviceFault[]
  models: PestModelVersion[]
  assessments: PestAssessment[]
  alerts: PestAlert[]
  events: MonitoringEvent[]
}

export interface StationCreatePayload {
  station_code: string
  station_name: string
  district_code: string
  longitude: number
  latitude: number
  station_type: StationType
  owner_department: string
  source_name: string
  source_uri: string
  source_version: string
  evidence_uri: string
  evidence_size_bytes: number
  evidence_sha256: string
  status: 'active' | 'maintenance' | 'retired'
  operator_code: string
}

export interface DeviceCreatePayload {
  device_code: string
  device_name: string
  device_type: DeviceType
  vendor: string
  model_number: string
  serial_number: string
  owner_department: string
  installed_at: string
  photo_uri: string
  photo_size_bytes: number
  photo_sha256: string
  status: DeviceStatus
  operator_code: string
}

export interface TelemetryCreatePayload {
  idempotency_key: string
  observed_at: string
  metric_code: string
  metric_value: number | null
  metric_unit: string | null
  payload: Record<string, unknown>
  evidence_uri?: string
  evidence_size_bytes?: number
  evidence_sha256?: string
  operator_code: string
}

export interface FaultCreatePayload {
  fault_code: string
  severity: FaultSeverity
  reason: string
  occurred_at: string
  operator_code: string
}

export interface FaultResolvePayload {
  resolution_comment: string
  resolution_evidence_uri: string
  resolution_evidence_size_bytes: number
  resolution_evidence_sha256: string
  operator_code: string
}

export interface PestModelCreatePayload {
  model_code: string
  model_version: string
  model_name: string
  target_type: 'pest' | 'disease'
  deployment_target: string
  training_source_uri: string
  evaluation_source_uri: string
  artifact_uri: string
  artifact_size_bytes: number
  artifact_sha256: string
  accuracy: number
  recall: number
  f1_score: number
  roc_auc: number
  operator_code: string
}

export interface AssessmentCreatePayload {
  assessment_code: string
  device_code?: string
  model_code: string
  model_version: string
  observed_at: string
  input_uri: string
  input_size_bytes: number
  input_sha256: string
  input_summary: Record<string, unknown>
  target_name: string
  prediction_label: string
  confidence: number
  prediction_basis: string
  operator_code: string
}

export interface AlertCreatePayload {
  alert_code: string
  risk_level: RiskLevel
  message: string
  channels: Array<'platform' | 'sms' | 'email' | 'mobile'>
  recipients: string[]
  operator_code: string
}
