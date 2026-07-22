-- 无人机航空器、飞行任务、实体成果、空间疑点和审计闭环。

CREATE TABLE IF NOT EXISTS uav_aircraft (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    aircraft_code VARCHAR(80) NOT NULL,
    aircraft_name VARCHAR(200) NOT NULL,
    manufacturer VARCHAR(150) NOT NULL,
    model_number VARCHAR(100) NOT NULL,
    serial_number VARCHAR(120) NOT NULL,
    registration_number VARCHAR(120) NOT NULL,
    sensor_name VARCHAR(150) NOT NULL,
    sensor_model VARCHAR(120) NOT NULL,
    sensor_serial_number VARCHAR(120) NOT NULL,
    owner_department VARCHAR(200) NOT NULL,
    certificate_uri VARCHAR(500) NOT NULL,
    certificate_filename VARCHAR(255) NOT NULL,
    certificate_size_bytes BIGINT NOT NULL CHECK (certificate_size_bytes > 0),
    certificate_sha256 VARCHAR(64) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    registered_by VARCHAR(100) NOT NULL,
    registered_by_code VARCHAR(50) NOT NULL,
    registered_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_uav_aircraft_code UNIQUE (project_id, aircraft_code)
);

CREATE INDEX IF NOT EXISTS idx_uav_aircraft_project_status
    ON uav_aircraft (project_id, status);

CREATE TABLE IF NOT EXISTS uav_missions (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    task_id INTEGER NOT NULL REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    aircraft_id INTEGER NOT NULL REFERENCES uav_aircraft(id) ON DELETE RESTRICT,
    mission_code VARCHAR(80) NOT NULL,
    mission_name VARCHAR(200) NOT NULL,
    district_code VARCHAR(50) NOT NULL,
    district_name VARCHAR(100) NOT NULL,
    flight_boundary geometry(POLYGON, 4326) NOT NULL,
    planned_area_ha NUMERIC(14, 4) NOT NULL CHECK (planned_area_ha > 0),
    pilot_name VARCHAR(100) NOT NULL,
    pilot_license_number VARCHAR(120) NOT NULL,
    pilot_license_uri VARCHAR(500) NOT NULL,
    pilot_license_filename VARCHAR(255) NOT NULL,
    pilot_license_size_bytes BIGINT NOT NULL CHECK (pilot_license_size_bytes > 0),
    pilot_license_sha256 VARCHAR(64) NOT NULL,
    planned_start_at TIMESTAMPTZ NOT NULL,
    planned_end_at TIMESTAMPTZ NOT NULL,
    actual_start_at TIMESTAMPTZ,
    actual_end_at TIMESTAMPTZ,
    altitude_m NUMERIC(8, 2) NOT NULL CHECK (altitude_m > 0),
    expected_resolution_cm NUMERIC(8, 3) NOT NULL CHECK (expected_resolution_cm > 0),
    forward_overlap_percent NUMERIC(5, 2) NOT NULL
        CHECK (forward_overlap_percent BETWEEN 0 AND 100),
    side_overlap_percent NUMERIC(5, 2) NOT NULL
        CHECK (side_overlap_percent BETWEEN 0 AND 100),
    weather_note TEXT NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'planned',
    cancellation_reason TEXT,
    created_by VARCHAR(100) NOT NULL,
    created_by_code VARCHAR(50) NOT NULL,
    created_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_uav_mission_code UNIQUE (project_id, mission_code),
    CONSTRAINT ck_uav_mission_schedule CHECK (planned_end_at > planned_start_at)
);

CREATE INDEX IF NOT EXISTS idx_uav_missions_project_status
    ON uav_missions (project_id, status, planned_start_at);
CREATE INDEX IF NOT EXISTS idx_uav_missions_task_region
    ON uav_missions (task_id, district_code);
CREATE INDEX IF NOT EXISTS idx_uav_missions_boundary_gist
    ON uav_missions USING GIST (flight_boundary);

CREATE TABLE IF NOT EXISTS uav_artifacts (
    id SERIAL PRIMARY KEY,
    mission_id INTEGER NOT NULL REFERENCES uav_missions(id) ON DELETE CASCADE,
    artifact_code VARCHAR(80) NOT NULL,
    artifact_type VARCHAR(40) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_uri VARCHAR(500) NOT NULL,
    file_size_bytes BIGINT NOT NULL CHECK (file_size_bytes > 0),
    checksum_sha256 VARCHAR(64) NOT NULL,
    captured_at TIMESTAMPTZ,
    file_format VARCHAR(40) NOT NULL,
    crs VARCHAR(100),
    resolution_cm NUMERIC(10, 3),
    raster_width INTEGER,
    raster_height INTEGER,
    footprint geometry(POLYGON, 4326),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    verification_status VARCHAR(30) NOT NULL DEFAULT 'verified',
    uploaded_by VARCHAR(100) NOT NULL,
    uploaded_by_code VARCHAR(50) NOT NULL,
    uploaded_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_uav_artifact_code UNIQUE (mission_id, artifact_code)
);

CREATE INDEX IF NOT EXISTS idx_uav_artifacts_mission_type
    ON uav_artifacts (mission_id, artifact_type, verification_status);
CREATE INDEX IF NOT EXISTS idx_uav_artifacts_footprint_gist
    ON uav_artifacts USING GIST (footprint);

CREATE TABLE IF NOT EXISTS uav_findings (
    id SERIAL PRIMARY KEY,
    mission_id INTEGER NOT NULL REFERENCES uav_missions(id) ON DELETE CASCADE,
    artifact_id INTEGER NOT NULL REFERENCES uav_artifacts(id) ON DELETE RESTRICT,
    finding_code VARCHAR(80) NOT NULL,
    finding_type VARCHAR(60) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    longitude NUMERIC(10, 7) NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    latitude NUMERIC(10, 7) NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    plot_code VARCHAR(50) REFERENCES farmland_plots(plot_code) ON DELETE SET NULL,
    description TEXT NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'pending_review',
    created_by VARCHAR(100) NOT NULL,
    created_by_code VARCHAR(50) NOT NULL,
    created_by_role VARCHAR(40) NOT NULL,
    review_comment TEXT,
    reviewed_by VARCHAR(100),
    reviewed_by_code VARCHAR(50),
    reviewed_by_role VARCHAR(40),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_uav_finding_code UNIQUE (mission_id, finding_code)
);

CREATE INDEX IF NOT EXISTS idx_uav_findings_mission_status
    ON uav_findings (mission_id, status, severity);
CREATE INDEX IF NOT EXISTS idx_uav_findings_plot
    ON uav_findings (plot_code) WHERE plot_code IS NOT NULL;

CREATE TABLE IF NOT EXISTS uav_events (
    id BIGSERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    mission_id INTEGER REFERENCES uav_missions(id) ON DELETE CASCADE,
    entity_type VARCHAR(40) NOT NULL,
    entity_code VARCHAR(80) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    actor VARCHAR(100) NOT NULL,
    actor_code VARCHAR(50) NOT NULL,
    actor_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_uav_events_project_time
    ON uav_events (project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_uav_events_mission_time
    ON uav_events (mission_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_uav_events_entity
    ON uav_events (entity_type, entity_code, created_at DESC);
