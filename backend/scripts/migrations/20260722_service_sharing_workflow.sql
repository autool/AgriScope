-- 新增受控地图/数据服务注册、审批、凭证、健康、调用审计和撤销闭环。

BEGIN;

CREATE TABLE IF NOT EXISTS shared_services (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL
        REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    service_code VARCHAR(80) NOT NULL,
    service_name VARCHAR(200) NOT NULL,
    service_type VARCHAR(30) NOT NULL,
    endpoint_url VARCHAR(1000) NOT NULL,
    health_check_url VARCHAR(1000) NOT NULL,
    documentation_url VARCHAR(1000) NOT NULL,
    resource_type VARCHAR(30) NOT NULL,
    resource_code VARCHAR(100) NOT NULL,
    resource_checksum_sha256 VARCHAR(64),
    data_classification VARCHAR(30) NOT NULL,
    exposure_scope VARCHAR(30) NOT NULL,
    auth_mode VARCHAR(30) NOT NULL,
    status VARCHAR(30) NOT NULL,
    owner_department VARCHAR(150) NOT NULL,
    registered_by VARCHAR(100) NOT NULL,
    registered_by_code VARCHAR(50) NOT NULL,
    registered_by_role VARCHAR(40) NOT NULL,
    reviewed_by VARCHAR(100),
    reviewed_by_code VARCHAR(50),
    reviewed_by_role VARCHAR(40),
    review_comment TEXT,
    reviewed_at TIMESTAMPTZ,
    revoked_by VARCHAR(100),
    revoked_by_code VARCHAR(50),
    revoked_by_role VARCHAR(40),
    revocation_reason TEXT,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_shared_service_project_code
        UNIQUE (project_id, service_code),
    CONSTRAINT ck_shared_service_type CHECK (
        service_type IN ('stac', 'wms', 'wmts', 'wfs', 'rest', 'download')
    ),
    CONSTRAINT ck_shared_service_resource_type CHECK (
        resource_type IN (
            'external_api', 'imagery', 'vector', 'thematic_map',
            'delivery', 'statistics', 'other'
        )
    ),
    CONSTRAINT ck_shared_service_classification CHECK (
        data_classification IN ('public', 'internal', 'confidential')
    ),
    CONSTRAINT ck_shared_service_scope CHECK (
        exposure_scope IN ('public', 'project', 'restricted')
    ),
    CONSTRAINT ck_shared_service_auth_mode CHECK (
        auth_mode IN ('none', 'api_key', 'oauth2', 'network_whitelist')
    ),
    CONSTRAINT ck_shared_service_status CHECK (
        status IN (
            'pending_approval', 'active', 'rejected', 'suspended', 'revoked'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_shared_services_project_status
    ON shared_services (project_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS service_access_requests (
    id SERIAL PRIMARY KEY,
    service_id INTEGER NOT NULL
        REFERENCES shared_services(id) ON DELETE CASCADE,
    request_code VARCHAR(100) NOT NULL UNIQUE,
    applicant_organization VARCHAR(200) NOT NULL,
    purpose TEXT NOT NULL,
    requested_until DATE NOT NULL,
    status VARCHAR(30) NOT NULL,
    applicant VARCHAR(100) NOT NULL,
    applicant_code VARCHAR(50) NOT NULL,
    applicant_role VARCHAR(40) NOT NULL,
    decided_by VARCHAR(100),
    decided_by_code VARCHAR(50),
    decided_by_role VARCHAR(40),
    decision_comment TEXT,
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_service_access_request_status CHECK (
        status IN ('pending', 'approved', 'rejected', 'revoked', 'expired')
    )
);

CREATE INDEX IF NOT EXISTS idx_service_access_requests_service_status
    ON service_access_requests (service_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS service_credentials (
    id SERIAL PRIMARY KEY,
    service_id INTEGER NOT NULL
        REFERENCES shared_services(id) ON DELETE CASCADE,
    access_request_id INTEGER NOT NULL UNIQUE
        REFERENCES service_access_requests(id) ON DELETE CASCADE,
    credential_code VARCHAR(100) NOT NULL UNIQUE,
    secret_hash VARCHAR(64) NOT NULL,
    secret_last_four VARCHAR(4) NOT NULL,
    status VARCHAR(20) NOT NULL,
    issued_by VARCHAR(100) NOT NULL,
    issued_by_code VARCHAR(50) NOT NULL,
    issued_by_role VARCHAR(40) NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_by VARCHAR(100),
    revoked_by_code VARCHAR(50),
    revoked_by_role VARCHAR(40),
    revocation_reason TEXT,
    revoked_at TIMESTAMPTZ,
    CONSTRAINT ck_service_credential_status CHECK (
        status IN ('active', 'revoked', 'expired')
    )
);

CREATE INDEX IF NOT EXISTS idx_service_credentials_service_status
    ON service_credentials (service_id, status, expires_at);

CREATE TABLE IF NOT EXISTS service_health_checks (
    id SERIAL PRIMARY KEY,
    service_id INTEGER NOT NULL
        REFERENCES shared_services(id) ON DELETE CASCADE,
    checked_url VARCHAR(1000) NOT NULL,
    status VARCHAR(30) NOT NULL,
    http_status INTEGER,
    response_time_ms INTEGER NOT NULL,
    detail VARCHAR(500) NOT NULL,
    checked_by VARCHAR(100) NOT NULL,
    checked_by_code VARCHAR(50) NOT NULL,
    checked_by_role VARCHAR(40) NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_service_health_check_status CHECK (
        status IN ('healthy', 'degraded', 'unavailable')
    )
);

CREATE INDEX IF NOT EXISTS idx_service_health_checks_service_time
    ON service_health_checks (service_id, checked_at DESC);

CREATE TABLE IF NOT EXISTS service_usage_events (
    id SERIAL PRIMARY KEY,
    service_id INTEGER NOT NULL
        REFERENCES shared_services(id) ON DELETE CASCADE,
    access_request_id INTEGER
        REFERENCES service_access_requests(id) ON DELETE SET NULL,
    credential_id INTEGER
        REFERENCES service_credentials(id) ON DELETE SET NULL,
    event_type VARCHAR(50) NOT NULL,
    request_method VARCHAR(10),
    request_path VARCHAR(1000),
    response_status INTEGER,
    duration_ms INTEGER,
    response_bytes BIGINT,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    actor VARCHAR(100) NOT NULL,
    actor_code VARCHAR(100) NOT NULL,
    actor_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_service_usage_events_service_time
    ON service_usage_events (service_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_service_usage_events_type_time
    ON service_usage_events (event_type, created_at DESC);

COMMIT;
