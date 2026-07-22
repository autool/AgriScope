-- 田间物联网监测、设备故障和病虫害模型复核告警闭环。

CREATE TABLE IF NOT EXISTS monitoring_stations (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    station_code VARCHAR(80) NOT NULL,
    station_name VARCHAR(200) NOT NULL,
    province_code VARCHAR(50) NOT NULL,
    province_name VARCHAR(100) NOT NULL,
    city_code VARCHAR(50) NOT NULL,
    city_name VARCHAR(100) NOT NULL,
    district_code VARCHAR(50) NOT NULL,
    district_name VARCHAR(100) NOT NULL,
    longitude NUMERIC(10, 7) NOT NULL,
    latitude NUMERIC(10, 7) NOT NULL,
    station_type VARCHAR(40) NOT NULL,
    owner_department VARCHAR(200) NOT NULL,
    source_name VARCHAR(120) NOT NULL,
    source_uri VARCHAR(500) NOT NULL,
    source_version VARCHAR(80) NOT NULL,
    evidence_uri VARCHAR(500) NOT NULL,
    evidence_size_bytes BIGINT NOT NULL CHECK (evidence_size_bytes > 0),
    evidence_sha256 VARCHAR(64) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    registered_by VARCHAR(100) NOT NULL,
    registered_by_code VARCHAR(50) NOT NULL,
    registered_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_station_code UNIQUE (project_id, station_code),
    CONSTRAINT ck_monitoring_station_longitude CHECK (longitude BETWEEN -180 AND 180),
    CONSTRAINT ck_monitoring_station_latitude CHECK (latitude BETWEEN -90 AND 90)
);

CREATE INDEX IF NOT EXISTS idx_monitoring_stations_project_region
    ON monitoring_stations (project_id, district_code, status);

CREATE TABLE IF NOT EXISTS monitoring_devices (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    station_id INTEGER NOT NULL REFERENCES monitoring_stations(id) ON DELETE CASCADE,
    device_code VARCHAR(80) NOT NULL,
    device_name VARCHAR(200) NOT NULL,
    device_type VARCHAR(50) NOT NULL,
    vendor VARCHAR(150) NOT NULL,
    model_number VARCHAR(100) NOT NULL,
    serial_number VARCHAR(120) NOT NULL,
    owner_department VARCHAR(200) NOT NULL,
    installed_at TIMESTAMPTZ NOT NULL,
    photo_uri VARCHAR(500) NOT NULL,
    photo_size_bytes BIGINT NOT NULL CHECK (photo_size_bytes > 0),
    photo_sha256 VARCHAR(64) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'offline',
    last_telemetry_at TIMESTAMPTZ,
    registered_by VARCHAR(100) NOT NULL,
    registered_by_code VARCHAR(50) NOT NULL,
    registered_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_device_code UNIQUE (project_id, device_code)
);

CREATE INDEX IF NOT EXISTS idx_monitoring_devices_station_status
    ON monitoring_devices (station_id, status);
CREATE INDEX IF NOT EXISTS idx_monitoring_devices_project_status
    ON monitoring_devices (project_id, status);

CREATE TABLE IF NOT EXISTS device_telemetry (
    id BIGSERIAL PRIMARY KEY,
    device_id INTEGER NOT NULL REFERENCES monitoring_devices(id) ON DELETE CASCADE,
    idempotency_key VARCHAR(120) NOT NULL,
    request_sha256 VARCHAR(64) NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    metric_code VARCHAR(80) NOT NULL,
    metric_value NUMERIC(18, 6),
    metric_unit VARCHAR(40),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_uri VARCHAR(500),
    evidence_size_bytes BIGINT,
    evidence_sha256 VARCHAR(64),
    ingested_by VARCHAR(100) NOT NULL,
    ingested_by_code VARCHAR(50) NOT NULL,
    ingested_by_role VARCHAR(40) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_device_telemetry_idempotency UNIQUE (device_id, idempotency_key),
    CONSTRAINT ck_device_telemetry_evidence_size
        CHECK (evidence_size_bytes IS NULL OR evidence_size_bytes > 0)
);

CREATE INDEX IF NOT EXISTS idx_device_telemetry_device_time
    ON device_telemetry (device_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_device_telemetry_metric_time
    ON device_telemetry (metric_code, observed_at DESC);

CREATE TABLE IF NOT EXISTS device_faults (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    device_id INTEGER NOT NULL REFERENCES monitoring_devices(id) ON DELETE CASCADE,
    fault_code VARCHAR(80) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    reason TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'open',
    reported_by VARCHAR(100) NOT NULL,
    reported_by_code VARCHAR(50) NOT NULL,
    reported_by_role VARCHAR(40) NOT NULL,
    resolution_comment TEXT,
    resolution_evidence_uri VARCHAR(500),
    resolution_evidence_size_bytes BIGINT,
    resolution_evidence_sha256 VARCHAR(64),
    resolved_by VARCHAR(100),
    resolved_by_code VARCHAR(50),
    resolved_by_role VARCHAR(40),
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_device_fault_code UNIQUE (project_id, fault_code),
    CONSTRAINT ck_device_fault_resolution_size
        CHECK (resolution_evidence_size_bytes IS NULL OR resolution_evidence_size_bytes > 0)
);

CREATE INDEX IF NOT EXISTS idx_device_faults_project_status
    ON device_faults (project_id, status, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_device_faults_device_status
    ON device_faults (device_id, status);

CREATE TABLE IF NOT EXISTS pest_model_versions (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    model_code VARCHAR(80) NOT NULL,
    model_version VARCHAR(80) NOT NULL,
    model_name VARCHAR(200) NOT NULL,
    target_type VARCHAR(30) NOT NULL,
    deployment_target VARCHAR(120) NOT NULL,
    training_source_uri VARCHAR(500) NOT NULL,
    evaluation_source_uri VARCHAR(500) NOT NULL,
    artifact_uri VARCHAR(500) NOT NULL,
    artifact_size_bytes BIGINT NOT NULL CHECK (artifact_size_bytes > 0),
    artifact_sha256 VARCHAR(64) NOT NULL,
    accuracy NUMERIC(7, 6) NOT NULL CHECK (accuracy BETWEEN 0 AND 1),
    recall NUMERIC(7, 6) NOT NULL CHECK (recall BETWEEN 0 AND 1),
    f1_score NUMERIC(7, 6) NOT NULL CHECK (f1_score BETWEEN 0 AND 1),
    roc_auc NUMERIC(7, 6) NOT NULL CHECK (roc_auc BETWEEN 0 AND 1),
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    superseded_by_version VARCHAR(80),
    registered_by VARCHAR(100) NOT NULL,
    registered_by_code VARCHAR(50) NOT NULL,
    registered_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_pest_model_version UNIQUE (project_id, model_code, model_version)
);

CREATE INDEX IF NOT EXISTS idx_pest_model_versions_project_status
    ON pest_model_versions (project_id, model_code, status);

CREATE TABLE IF NOT EXISTS pest_assessments (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    device_id INTEGER REFERENCES monitoring_devices(id) ON DELETE SET NULL,
    model_version_id INTEGER NOT NULL REFERENCES pest_model_versions(id) ON DELETE RESTRICT,
    assessment_code VARCHAR(80) NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    input_uri VARCHAR(500) NOT NULL,
    input_size_bytes BIGINT NOT NULL CHECK (input_size_bytes > 0),
    input_sha256 VARCHAR(64) NOT NULL,
    input_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    target_name VARCHAR(150) NOT NULL,
    prediction_label VARCHAR(150) NOT NULL,
    confidence NUMERIC(7, 6) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    prediction_basis TEXT NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'pending_review',
    submitted_by VARCHAR(100) NOT NULL,
    submitted_by_code VARCHAR(50) NOT NULL,
    submitted_by_role VARCHAR(40) NOT NULL,
    review_comment TEXT,
    reviewed_by VARCHAR(100),
    reviewed_by_code VARCHAR(50),
    reviewed_by_role VARCHAR(40),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_pest_assessment_code UNIQUE (project_id, assessment_code)
);

CREATE INDEX IF NOT EXISTS idx_pest_assessments_project_status
    ON pest_assessments (project_id, status, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_pest_assessments_model
    ON pest_assessments (model_version_id, created_at DESC);

CREATE TABLE IF NOT EXISTS pest_alerts (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    assessment_id INTEGER NOT NULL REFERENCES pest_assessments(id) ON DELETE CASCADE,
    alert_code VARCHAR(80) NOT NULL,
    risk_level VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    channels JSONB NOT NULL DEFAULT '[]'::jsonb,
    recipients JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    created_by VARCHAR(100) NOT NULL,
    created_by_code VARCHAR(50) NOT NULL,
    created_by_role VARCHAR(40) NOT NULL,
    delivery_receipt_uri VARCHAR(500),
    delivery_receipt_size_bytes BIGINT,
    delivery_receipt_sha256 VARCHAR(64),
    delivered_by VARCHAR(100),
    delivered_by_code VARCHAR(50),
    delivered_by_role VARCHAR(40),
    delivered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_pest_alert_code UNIQUE (project_id, alert_code),
    CONSTRAINT uq_pest_alert_assessment UNIQUE (assessment_id),
    CONSTRAINT ck_pest_alert_receipt_size
        CHECK (delivery_receipt_size_bytes IS NULL OR delivery_receipt_size_bytes > 0)
);

CREATE INDEX IF NOT EXISTS idx_pest_alerts_project_status
    ON pest_alerts (project_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS monitoring_events (
    id BIGSERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    entity_type VARCHAR(40) NOT NULL,
    entity_code VARCHAR(80) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    actor VARCHAR(100) NOT NULL,
    actor_code VARCHAR(50) NOT NULL,
    actor_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_monitoring_events_project_time
    ON monitoring_events (project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_monitoring_events_entity
    ON monitoring_events (entity_type, entity_code, created_at DESC);
