export type SharedServiceStatus =
  | 'pending_approval'
  | 'active'
  | 'rejected'
  | 'suspended'
  | 'revoked'

export interface ServiceHealth {
  status: 'healthy' | 'degraded' | 'unavailable'
  http_status: number | null
  response_time_ms: number
  detail: string
  checked_by: string
  checked_at: string
}

export interface ServiceCredential {
  credential_code: string
  secret_last_four: string
  status: 'active' | 'revoked' | 'expired'
  issued_at: string
  expires_at: string
}

export interface ServiceAccessRequest {
  request_code: string
  service_code: string
  applicant_organization: string
  purpose: string
  requested_until: string
  status: 'pending' | 'approved' | 'rejected' | 'revoked' | 'expired'
  applicant: string
  applicant_code: string
  applicant_role: string
  decision_comment: string | null
  created_at: string
  decided_at: string | null
  credential: ServiceCredential | null
}

export interface SharedService {
  service_code: string
  service_name: string
  service_type: 'stac' | 'wms' | 'wmts' | 'wfs' | 'rest' | 'download'
  endpoint_url: string
  health_check_url: string
  documentation_url: string
  resource_type: string
  resource_code: string
  resource_checksum_sha256: string | null
  data_classification: 'public' | 'internal' | 'confidential'
  exposure_scope: 'public' | 'project' | 'restricted'
  auth_mode: 'none' | 'api_key' | 'oauth2' | 'network_whitelist'
  status: SharedServiceStatus
  owner_department: string
  registered_by: string
  registered_by_code: string
  registered_by_role: string
  reviewed_by: string | null
  review_comment: string | null
  created_at: string
  updated_at: string
  latest_health: ServiceHealth | null
  access_request_count: number
  active_credential_count: number
  usage_count: number
}

export interface ServiceUsageEvent {
  event_type: string
  service_code: string
  actor: string
  actor_code: string
  actor_role: string
  request_method: string | null
  request_path: string | null
  response_status: number | null
  duration_ms: number | null
  response_bytes: number | null
  detail: Record<string, unknown>
  created_at: string
}

export interface ServiceSharingOverview {
  project_code: string
  service_count: number
  active_service_count: number
  pending_approval_count: number
  pending_access_count: number
  healthy_service_count: number
  services: SharedService[]
  access_requests: ServiceAccessRequest[]
  events: ServiceUsageEvent[]
}

export interface ServiceRegistrationPayload {
  service_code: string
  service_name: string
  service_type: SharedService['service_type']
  endpoint_url: string
  health_check_url: string
  documentation_url: string
  resource_type: string
  resource_code: string
  resource_checksum_sha256?: string | null
  data_classification: SharedService['data_classification']
  exposure_scope: SharedService['exposure_scope']
  auth_mode: SharedService['auth_mode']
  owner_department: string
  operator_code: string
}

export interface ServiceReviewPayload {
  decision: 'approve' | 'reject'
  comment: string
  operator_code: string
}

export interface ServiceAccessRequestPayload {
  applicant_organization: string
  purpose: string
  requested_until: string
  operator_code: string
}

export interface ServiceAccessReviewResult {
  request: ServiceAccessRequest
  credential_secret: string | null
}
