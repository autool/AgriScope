import request from '@/api/request'
import type {
  ServiceAccessRequest,
  ServiceAccessRequestPayload,
  ServiceAccessReviewResult,
  ServiceHealth,
  ServiceRegistrationPayload,
  ServiceReviewPayload,
  ServiceSharingOverview,
  SharedService,
} from '@/types/serviceSharing'

const projectParams = (projectCode: string) => ({ project_code: projectCode })

export const getServiceSharingOverview = (
  projectCode: string,
  operatorCode: string,
) => request.get<ServiceSharingOverview>('/v1/service-sharing/overview', {
  params: { ...projectParams(projectCode), operator_code: operatorCode },
})

export const registerSharedService = (
  projectCode: string,
  payload: ServiceRegistrationPayload,
) => request.post<SharedService>('/v1/service-sharing/services', payload, {
  params: projectParams(projectCode),
})

export const reviewSharedService = (
  projectCode: string,
  serviceCode: string,
  payload: ServiceReviewPayload,
) => request.post<SharedService>(
  `/v1/service-sharing/services/${encodeURIComponent(serviceCode)}/review`,
  payload,
  { params: projectParams(projectCode) },
)

export const createServiceAccessRequest = (
  projectCode: string,
  serviceCode: string,
  payload: ServiceAccessRequestPayload,
) => request.post<ServiceAccessRequest>(
  `/v1/service-sharing/services/${encodeURIComponent(serviceCode)}/access-requests`,
  payload,
  { params: projectParams(projectCode) },
)

export const reviewServiceAccessRequest = (
  projectCode: string,
  requestCode: string,
  payload: ServiceReviewPayload,
) => request.post<ServiceAccessReviewResult>(
  `/v1/service-sharing/access-requests/${encodeURIComponent(requestCode)}/review`,
  payload,
  { params: projectParams(projectCode) },
)

export const runSharedServiceHealthCheck = (
  projectCode: string,
  serviceCode: string,
  operatorCode: string,
) => request.post<ServiceHealth>(
  `/v1/service-sharing/services/${encodeURIComponent(serviceCode)}/health-check`,
  { operator_code: operatorCode },
  { params: projectParams(projectCode) },
)

export const revokeSharedService = (
  projectCode: string,
  serviceCode: string,
  reason: string,
  operatorCode: string,
) => request.post<SharedService>(
  `/v1/service-sharing/services/${encodeURIComponent(serviceCode)}/revoke`,
  { reason, operator_code: operatorCode },
  { params: projectParams(projectCode) },
)

export const revokeServiceCredential = (
  projectCode: string,
  credentialCode: string,
  reason: string,
  operatorCode: string,
) => request.post(
  `/v1/service-sharing/credentials/${encodeURIComponent(credentialCode)}/revoke`,
  { reason, operator_code: operatorCode },
  { params: projectParams(projectCode) },
)
