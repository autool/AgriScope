export type UavArtifactType =
  | 'raw_imagery'
  | 'flight_log'
  | 'photo'
  | 'video'
  | 'orthomosaic'
  | 'dem'
  | 'report'

export interface UavPolygon {
  type: 'Polygon'
  coordinates: Array<Array<[number, number]>>
}

export type UavMissionAction =
  | 'start'
  | 'complete_capture'
  | 'complete_processing'
  | 'complete_review'
  | 'cancel'

export interface UavAircraft {
  aircraft_code: string
  aircraft_name: string
  manufacturer: string
  model_number: string
  serial_number: string
  registration_number: string
  sensor_name: string
  sensor_model: string
  sensor_serial_number: string
  owner_department: string
  certificate_uri: string
  certificate_filename: string
  certificate_size_bytes: number
  certificate_sha256: string
  status: 'active' | 'maintenance' | 'retired'
  registered_by: string
  registered_by_code: string
  registered_by_role: string
  created_at: string
}

export interface UavMission {
  mission_code: string
  mission_name: string
  task_code: string
  aircraft_code: string
  aircraft_name: string
  district_code: string
  district_name: string
  flight_boundary: UavPolygon
  planned_area_ha: number
  pilot_name: string
  pilot_license_number: string
  pilot_license_uri: string
  pilot_license_filename: string
  pilot_license_size_bytes: number
  pilot_license_sha256: string
  planned_start_at: string
  planned_end_at: string
  actual_start_at: string | null
  actual_end_at: string | null
  altitude_m: number
  expected_resolution_cm: number
  forward_overlap_percent: number
  side_overlap_percent: number
  weather_note: string
  status: 'planned' | 'in_progress' | 'captured' | 'processed' | 'reviewed' | 'cancelled'
  cancellation_reason: string | null
  created_by: string
  created_by_code: string
  created_by_role: string
  created_at: string
}

export interface UavArtifact {
  mission_code: string
  artifact_code: string
  artifact_type: UavArtifactType
  original_filename: string
  file_uri: string
  file_size_bytes: number
  checksum_sha256: string
  captured_at: string | null
  file_format: string
  crs: string | null
  resolution_cm: number | null
  raster_width: number | null
  raster_height: number | null
  footprint: UavPolygon | null
  metadata: Record<string, unknown>
  verification_status: 'verified'
  uploaded_by: string
  uploaded_by_code: string
  uploaded_by_role: string
  created_at: string
}

export interface UavFinding {
  mission_code: string
  artifact_code: string
  finding_code: string
  finding_type: string
  severity: 'minor' | 'major' | 'critical'
  longitude: number
  latitude: number
  plot_code: string | null
  description: string
  status: 'pending_review' | 'confirmed' | 'dismissed'
  created_by: string
  created_by_code: string
  created_by_role: string
  review_comment: string | null
  reviewed_by: string | null
  reviewed_by_code: string | null
  reviewed_by_role: string | null
  reviewed_at: string | null
  created_at: string
}

export interface UavEvent {
  entity_type: string
  entity_code: string
  event_type: string
  detail: Record<string, unknown>
  actor: string
  actor_code: string
  actor_role: string
  created_at: string
}

export interface UavOverview {
  aircraft_count: number
  mission_count: number
  active_mission_count: number
  pending_processing_count: number
  pending_finding_count: number
  verified_artifact_count: number
  aircraft: UavAircraft[]
  missions: UavMission[]
  artifacts: UavArtifact[]
  findings: UavFinding[]
  events: UavEvent[]
}

export interface AircraftUploadMetadata {
  aircraftCode: string
  aircraftName: string
  manufacturer: string
  modelNumber: string
  serialNumber: string
  registrationNumber: string
  sensorName: string
  sensorModel: string
  sensorSerialNumber: string
  ownerDepartment: string
}

export interface MissionUploadMetadata {
  missionCode: string
  missionName: string
  aircraftCode: string
  districtCode: string
  flightBoundary: UavPolygon
  pilotName: string
  pilotLicenseNumber: string
  plannedStartAt: string
  plannedEndAt: string
  altitudeM: number
  expectedResolutionCm: number
  forwardOverlapPercent: number
  sideOverlapPercent: number
  weatherNote: string
}

export interface ArtifactUploadMetadata {
  artifactCode: string
  artifactType: UavArtifactType
  capturedAt: string | null
  sourceName: string
  sourceVersion: string
  metadata: Record<string, unknown>
}

export interface UavFindingCreatePayload {
  finding_code: string
  artifact_code: string
  finding_type: string
  severity: 'minor' | 'major' | 'critical'
  longitude: number
  latitude: number
  plot_code?: string
  description: string
  operator_code: string
}
