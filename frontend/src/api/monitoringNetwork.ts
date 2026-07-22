import request from '@/api/request'
import type {
  AlertCreatePayload,
  AssessmentCreatePayload,
  DeviceCreatePayload,
  FaultCreatePayload,
  FaultResolvePayload,
  MonitoringDevice,
  MonitoringOverview,
  MonitoringStation,
  PestAlert,
  PestAssessment,
  PestModelCreatePayload,
  PestModelVersion,
  StationCreatePayload,
  TelemetryCreatePayload,
  DeviceFault,
  DeviceTelemetry,
} from '@/types/monitoringNetwork'

const projectQuery = (projectCode: string) => ({ project_code: projectCode })

export const getMonitoringOverview = (
  projectCode: string,
  operatorCode: string,
) => request.get<MonitoringOverview>('/v1/monitoring-network/overview', {
  params: { ...projectQuery(projectCode), operator_code: operatorCode },
})

export const createMonitoringStation = (
  projectCode: string,
  payload: StationCreatePayload,
) => request.post<MonitoringStation>(
  '/v1/monitoring-network/stations',
  payload,
  { params: projectQuery(projectCode) },
)

export const createMonitoringDevice = (
  projectCode: string,
  stationCode: string,
  payload: DeviceCreatePayload,
) => request.post<MonitoringDevice>(
  `/v1/monitoring-network/stations/${encodeURIComponent(stationCode)}/devices`,
  payload,
  { params: projectQuery(projectCode) },
)

export const createDeviceTelemetry = (
  projectCode: string,
  deviceCode: string,
  payload: TelemetryCreatePayload,
) => request.post<DeviceTelemetry>(
  `/v1/monitoring-network/devices/${encodeURIComponent(deviceCode)}/telemetry`,
  payload,
  { params: projectQuery(projectCode) },
)

export const createDeviceFault = (
  projectCode: string,
  deviceCode: string,
  payload: FaultCreatePayload,
) => request.post<DeviceFault>(
  `/v1/monitoring-network/devices/${encodeURIComponent(deviceCode)}/faults`,
  payload,
  { params: projectQuery(projectCode) },
)

export const resolveDeviceFault = (
  projectCode: string,
  faultCode: string,
  payload: FaultResolvePayload,
) => request.post<DeviceFault>(
  `/v1/monitoring-network/faults/${encodeURIComponent(faultCode)}/resolve`,
  payload,
  { params: projectQuery(projectCode) },
)

export const createPestModel = (
  projectCode: string,
  payload: PestModelCreatePayload,
) => request.post<PestModelVersion>(
  '/v1/monitoring-network/models',
  payload,
  { params: projectQuery(projectCode) },
)

export const createPestAssessment = (
  projectCode: string,
  payload: AssessmentCreatePayload,
) => request.post<PestAssessment>(
  '/v1/monitoring-network/assessments',
  payload,
  { params: projectQuery(projectCode) },
)

export const reviewPestAssessment = (
  projectCode: string,
  assessmentCode: string,
  decision: 'approve' | 'reject',
  comment: string,
  operatorCode: string,
) => request.post<PestAssessment>(
  `/v1/monitoring-network/assessments/${encodeURIComponent(assessmentCode)}/review`,
  { decision, comment, operator_code: operatorCode },
  { params: projectQuery(projectCode) },
)

export const createPestAlert = (
  projectCode: string,
  assessmentCode: string,
  payload: AlertCreatePayload,
) => request.post<PestAlert>(
  `/v1/monitoring-network/assessments/${encodeURIComponent(assessmentCode)}/alerts`,
  payload,
  { params: projectQuery(projectCode) },
)

export const deliverPestAlert = (
  projectCode: string,
  alertCode: string,
  receiptUri: string,
  receiptSizeBytes: number,
  receiptSha256: string,
  operatorCode: string,
) => request.post<PestAlert>(
  `/v1/monitoring-network/alerts/${encodeURIComponent(alertCode)}/deliver`,
  {
    delivery_receipt_uri: receiptUri,
    delivery_receipt_size_bytes: receiptSizeBytes,
    delivery_receipt_sha256: receiptSha256,
    operator_code: operatorCode,
  },
  { params: projectQuery(projectCode) },
)
