BEGIN;

CREATE TABLE IF NOT EXISTS imagery_mosaic_jobs (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    task_id INTEGER NOT NULL REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    job_code VARCHAR(80) NOT NULL,
    job_name VARCHAR(200) NOT NULL,
    boundary_code VARCHAR(50) NOT NULL,
    boundary_name VARCHAR(100) NOT NULL,
    target_crs VARCHAR(100) NOT NULL,
    target_resolution NUMERIC(16, 8) NOT NULL,
    color_balance_method VARCHAR(30) NOT NULL,
    blend_method VARCHAR(20) NOT NULL,
    resampling_method VARCHAR(20) NOT NULL,
    coverage_threshold NUMERIC(6, 3) NOT NULL,
    coverage_ratio NUMERIC(6, 3) NOT NULL,
    boundary_pixel_count BIGINT NOT NULL,
    covered_pixel_count BIGINT NOT NULL,
    source_count INTEGER NOT NULL,
    raster_width INTEGER NOT NULL,
    raster_height INTEGER NOT NULL,
    band_count INTEGER NOT NULL,
    dtype VARCHAR(30) NOT NULL,
    output_uri VARCHAR(500) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    bounds_wgs84 JSONB NOT NULL DEFAULT '[]'::jsonb,
    manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by VARCHAR(100) NOT NULL,
    created_by_code VARCHAR(50) NOT NULL,
    created_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_imagery_mosaic_job UNIQUE (project_id, job_code)
);

CREATE INDEX IF NOT EXISTS idx_imagery_mosaic_jobs_project_time
    ON imagery_mosaic_jobs (project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS imagery_mosaic_inputs (
    id BIGSERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES imagery_mosaic_jobs(id) ON DELETE CASCADE,
    asset_id INTEGER NOT NULL REFERENCES imagery_assets(id) ON DELETE RESTRICT,
    asset_code VARCHAR(80) NOT NULL,
    asset_name VARCHAR(200) NOT NULL,
    step_code VARCHAR(50) NOT NULL,
    step_name VARCHAR(100) NOT NULL,
    source_order INTEGER NOT NULL,
    source_uri VARCHAR(500) NOT NULL,
    source_size_bytes BIGINT NOT NULL,
    source_sha256 VARCHAR(64) NOT NULL,
    source_crs VARCHAR(100) NOT NULL,
    source_width INTEGER NOT NULL,
    source_height INTEGER NOT NULL,
    source_band_count INTEGER NOT NULL,
    band_descriptions JSONB NOT NULL DEFAULT '[]'::jsonb,
    balance_statistics JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_imagery_mosaic_input UNIQUE (job_id, asset_id, step_code)
);

CREATE INDEX IF NOT EXISTS idx_imagery_mosaic_inputs_job_order
    ON imagery_mosaic_inputs (job_id, source_order);

CREATE TABLE IF NOT EXISTS imagery_mosaic_events (
    id BIGSERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    job_id INTEGER NOT NULL REFERENCES imagery_mosaic_jobs(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    actor_code VARCHAR(50) NOT NULL,
    actor_role VARCHAR(40) NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_imagery_mosaic_events_job_time
    ON imagery_mosaic_events (job_id, created_at DESC);

COMMIT;
