BEGIN;

CREATE TABLE IF NOT EXISTS imagery_registration_jobs (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    task_id INTEGER NOT NULL REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    job_code VARCHAR(80) NOT NULL,
    job_name VARCHAR(200) NOT NULL,
    reference_asset_id INTEGER NOT NULL REFERENCES imagery_assets(id) ON DELETE RESTRICT,
    moving_asset_id INTEGER NOT NULL REFERENCES imagery_assets(id) ON DELETE RESTRICT,
    reference_asset_code VARCHAR(80) NOT NULL,
    moving_asset_code VARCHAR(80) NOT NULL,
    reference_step_code VARCHAR(50) NOT NULL,
    moving_step_code VARCHAR(50) NOT NULL,
    reference_uri VARCHAR(500) NOT NULL,
    reference_size_bytes BIGINT NOT NULL,
    reference_sha256 VARCHAR(64) NOT NULL,
    moving_uri VARCHAR(500) NOT NULL,
    moving_size_bytes BIGINT NOT NULL,
    moving_sha256 VARCHAR(64) NOT NULL,
    reference_band_index INTEGER NOT NULL,
    moving_band_index INTEGER NOT NULL,
    resampling_method VARCHAR(20) NOT NULL,
    initial_shift_x_pixels NUMERIC(10, 4) NOT NULL,
    initial_shift_y_pixels NUMERIC(10, 4) NOT NULL,
    initial_offset_pixels NUMERIC(10, 4) NOT NULL,
    residual_shift_x_pixels NUMERIC(10, 4) NOT NULL,
    residual_shift_y_pixels NUMERIC(10, 4) NOT NULL,
    residual_offset_pixels NUMERIC(10, 4) NOT NULL,
    overlap_ratio NUMERIC(7, 5) NOT NULL,
    peak_to_sidelobe_ratio NUMERIC(12, 5) NOT NULL,
    residual_threshold_pixels NUMERIC(8, 3) NOT NULL,
    output_uri VARCHAR(500) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    output_crs VARCHAR(100) NOT NULL,
    output_resolution_x NUMERIC(16, 8) NOT NULL,
    output_resolution_y NUMERIC(16, 8) NOT NULL,
    raster_width INTEGER NOT NULL,
    raster_height INTEGER NOT NULL,
    band_count INTEGER NOT NULL,
    dtype VARCHAR(30) NOT NULL,
    bounds_wgs84 JSONB NOT NULL DEFAULT '[]'::jsonb,
    manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by VARCHAR(100) NOT NULL,
    created_by_code VARCHAR(50) NOT NULL,
    created_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_imagery_registration_job UNIQUE (project_id, job_code),
    CONSTRAINT ck_imagery_registration_distinct_assets CHECK (
        reference_asset_id <> moving_asset_id
    ),
    CONSTRAINT ck_imagery_registration_metrics CHECK (
        reference_band_index > 0
        AND moving_band_index > 0
        AND initial_offset_pixels >= 0
        AND residual_offset_pixels >= 0
        AND overlap_ratio > 0
        AND overlap_ratio <= 1
        AND peak_to_sidelobe_ratio > 0
        AND residual_threshold_pixels > 0
        AND residual_offset_pixels <= residual_threshold_pixels
        AND file_size_bytes > 0
        AND raster_width > 0
        AND raster_height > 0
        AND band_count > 0
    )
);

CREATE INDEX IF NOT EXISTS idx_imagery_registration_jobs_project_time
    ON imagery_registration_jobs (project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_imagery_registration_jobs_pair
    ON imagery_registration_jobs (
        project_id,
        reference_asset_id,
        moving_asset_id,
        created_at DESC
    );

CREATE TABLE IF NOT EXISTS imagery_registration_events (
    id BIGSERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    job_id INTEGER NOT NULL REFERENCES imagery_registration_jobs(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    actor_code VARCHAR(50) NOT NULL,
    actor_role VARCHAR(40) NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_imagery_registration_events_job_time
    ON imagery_registration_events (job_id, created_at DESC);

COMMIT;
