import request from '@/api/request'
import type {
  AircraftUploadMetadata,
  ArtifactUploadMetadata,
  MissionUploadMetadata,
  UavAircraft,
  UavArtifact,
  UavFinding,
  UavFindingCreatePayload,
  UavMission,
  UavMissionAction,
  UavOverview,
} from '@/types/uav'

const multipartConfig = (projectCode: string) => ({
  params: { project_code: projectCode },
  headers: { 'Content-Type': 'multipart/form-data' },
  timeout: 300_000,
})

export const getUavOverview = (
  projectCode: string,
  operatorCode: string,
) => request.get<UavOverview>('/v1/uav/overview', {
  params: { project_code: projectCode, operator_code: operatorCode },
})

export const registerUavAircraft = (
  projectCode: string,
  file: File,
  metadata: AircraftUploadMetadata,
  operatorCode: string,
) => {
  const formData = new FormData()
  formData.append('certificate_file', file)
  formData.append('aircraft_code', metadata.aircraftCode)
  formData.append('aircraft_name', metadata.aircraftName)
  formData.append('manufacturer', metadata.manufacturer)
  formData.append('model_number', metadata.modelNumber)
  formData.append('serial_number', metadata.serialNumber)
  formData.append('registration_number', metadata.registrationNumber)
  formData.append('sensor_name', metadata.sensorName)
  formData.append('sensor_model', metadata.sensorModel)
  formData.append('sensor_serial_number', metadata.sensorSerialNumber)
  formData.append('owner_department', metadata.ownerDepartment)
  formData.append('operator_code', operatorCode)
  formData.append('aircraft_status', 'active')
  return request.post<UavAircraft>(
    '/v1/uav/aircraft',
    formData,
    multipartConfig(projectCode),
  )
}

export const createUavMission = (
  projectCode: string,
  taskCode: string,
  file: File,
  metadata: MissionUploadMetadata,
  operatorCode: string,
) => {
  const formData = new FormData()
  formData.append('pilot_license_file', file)
  formData.append('mission_code', metadata.missionCode)
  formData.append('mission_name', metadata.missionName)
  formData.append('aircraft_code', metadata.aircraftCode)
  formData.append('district_code', metadata.districtCode)
  formData.append('flight_boundary_json', JSON.stringify(metadata.flightBoundary))
  formData.append('pilot_name', metadata.pilotName)
  formData.append('pilot_license_number', metadata.pilotLicenseNumber)
  formData.append('planned_start_at', metadata.plannedStartAt)
  formData.append('planned_end_at', metadata.plannedEndAt)
  formData.append('altitude_m', String(metadata.altitudeM))
  formData.append('expected_resolution_cm', String(metadata.expectedResolutionCm))
  formData.append('forward_overlap_percent', String(metadata.forwardOverlapPercent))
  formData.append('side_overlap_percent', String(metadata.sideOverlapPercent))
  formData.append('weather_note', metadata.weatherNote)
  formData.append('operator_code', operatorCode)
  return request.post<UavMission>('/v1/uav/missions', formData, {
    ...multipartConfig(projectCode),
    params: { project_code: projectCode, task_code: taskCode },
  })
}

export const uploadUavArtifact = (
  projectCode: string,
  missionCode: string,
  file: File,
  metadata: ArtifactUploadMetadata,
  operatorCode: string,
) => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('artifact_code', metadata.artifactCode)
  formData.append('artifact_type', metadata.artifactType)
  formData.append('source_name', metadata.sourceName)
  formData.append('source_version', metadata.sourceVersion)
  formData.append('metadata_json', JSON.stringify(metadata.metadata))
  formData.append('operator_code', operatorCode)
  if (metadata.capturedAt) formData.append('captured_at', metadata.capturedAt)
  return request.post<UavArtifact>(
    `/v1/uav/missions/${encodeURIComponent(missionCode)}/artifacts`,
    formData,
    multipartConfig(projectCode),
  )
}

export const transitionUavMission = (
  projectCode: string,
  missionCode: string,
  action: UavMissionAction,
  comment: string,
  actualTime: string | null,
  operatorCode: string,
) => request.post<UavMission>(
  `/v1/uav/missions/${encodeURIComponent(missionCode)}/status`,
  {
    action,
    comment,
    actual_time: actualTime,
    operator_code: operatorCode,
  },
  { params: { project_code: projectCode } },
)

export const createUavFinding = (
  projectCode: string,
  missionCode: string,
  payload: UavFindingCreatePayload,
) => request.post<UavFinding>(
  `/v1/uav/missions/${encodeURIComponent(missionCode)}/findings`,
  payload,
  { params: { project_code: projectCode } },
)

export const reviewUavFinding = (
  projectCode: string,
  missionCode: string,
  findingCode: string,
  decision: 'confirm' | 'dismiss',
  comment: string,
  operatorCode: string,
) => request.post<UavFinding>(
  `/v1/uav/missions/${encodeURIComponent(missionCode)}/findings/${encodeURIComponent(findingCode)}/review`,
  { decision, comment, operator_code: operatorCode },
  { params: { project_code: projectCode } },
)

export const downloadUavArtifact = (
  projectCode: string,
  artifactCode: string,
  operatorCode: string,
) => request.get<Blob>(
  `/v1/uav/artifacts/${encodeURIComponent(artifactCode)}/download`,
  {
    params: { project_code: projectCode, operator_code: operatorCode },
    responseType: 'blob',
    timeout: 300_000,
  },
)
