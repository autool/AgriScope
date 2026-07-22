import request from '@/api/request'
import type {
  AlertCreatePayload,
  AssessmentCreatePayload,
  ConsultationAnswerMetadata,
  ConsultationCreatePayload,
  DeviceCreatePayload,
  FaultCreatePayload,
  FaultResolvePayload,
  MonitoringDevice,
  MonitoringOverview,
  MonitoringStation,
  PestAlert,
  PestAssessment,
  PestReport,
  PestReportCreatePayload,
  PestReportRevisePayload,
  PestModelCreatePayload,
  PestModelVersion,
  StationCreatePayload,
  TelemetryCreatePayload,
  DeviceFault,
  DeviceTelemetry,
  ExpertConsultation,
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

export const createPestReport = (
  projectCode: string,
  payload: PestReportCreatePayload,
) => request.post<PestReport>(
  '/v1/monitoring-network/reports',
  payload,
  { params: projectQuery(projectCode) },
)

export const revisePestReport = (
  projectCode: string,
  reportCode: string,
  payload: PestReportRevisePayload,
) => request.patch<PestReport>(
  `/v1/monitoring-network/reports/${encodeURIComponent(reportCode)}`,
  payload,
  { params: projectQuery(projectCode) },
)

export const createExpertConsultation = (
  projectCode: string,
  reportCode: string,
  payload: ConsultationCreatePayload,
) => request.post<ExpertConsultation>(
  `/v1/monitoring-network/reports/${encodeURIComponent(reportCode)}/consultations`,
  payload,
  { params: projectQuery(projectCode) },
)

export const answerExpertConsultation = (
  projectCode: string,
  consultationCode: string,
  file: File,
  metadata: ConsultationAnswerMetadata,
  operatorCode: string,
) => {
  const formData = new FormData()
  formData.append('evidence_file', file)
  formData.append('expert_organization', metadata.expertOrganization)
  formData.append('expert_title', metadata.expertTitle)
  formData.append('response', metadata.response)
  formData.append('operator_code', operatorCode)
  return request.post<ExpertConsultation>(
    `/v1/monitoring-network/consultations/${encodeURIComponent(consultationCode)}/answer`,
    formData,
    {
      params: projectQuery(projectCode),
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300_000,
    },
  )
}

export const submitPestReport = (
  projectCode: string,
  reportCode: string,
  comment: string,
  operatorCode: string,
) => request.post<PestReport>(
  `/v1/monitoring-network/reports/${encodeURIComponent(reportCode)}/submit`,
  { comment, operator_code: operatorCode },
  { params: projectQuery(projectCode) },
)

export const reviewPestReport = (
  projectCode: string,
  reportCode: string,
  action: 'approve' | 'return',
  comment: string,
  operatorCode: string,
) => request.post<PestReport>(
  `/v1/monitoring-network/reports/${encodeURIComponent(reportCode)}/review`,
  { action, comment, operator_code: operatorCode },
  { params: projectQuery(projectCode) },
)

export const downloadPestReport = (
  projectCode: string,
  reportCode: string,
  operatorCode: string,
) => request.get<Blob>(
  `/v1/monitoring-network/reports/${encodeURIComponent(reportCode)}/download`,
  {
    params: { ...projectQuery(projectCode), operator_code: operatorCode },
    responseType: 'blob',
    timeout: 300_000,
  },
)
