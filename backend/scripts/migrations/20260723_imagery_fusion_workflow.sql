-- 新增多光谱/全色实体融合、质量验收和下载审计。

CREATE TABLE IF NOT EXISTS imagery_fusion_jobs (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    task_id INTEGER NOT NULL REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    job_code VARCHAR(80) NOT NULL,
    job_name VARCHAR(200) NOT NULL,
    multispectral_asset_id INTEGER NOT NULL REFERENCES imagery_assets(id) ON DELETE RESTRICT,
    multispectral_asset_code VARCHAR(80) NOT NULL,
    multispectral_asset_name VARCHAR(200) NOT NULL,
    panchromatic_asset_id INTEGER NOT NULL REFERENCES imagery_assets(id) ON DELETE RESTRICT,
    panchromatic_asset_code VARCHAR(80) NOT NULL,
    panchromatic_asset_name VARCHAR(200) NOT NULL,
    multispectral_band_indexes JSONB NOT NULL,
    panchromatic_band_index INTEGER NOT NULL,
    algorithm_code VARCHAR(50) NOT NULL,
    algorithm_version VARCHAR(80) NOT NULL,
    resampling_method VARCHAR(20) NOT NULL,
    overlap_ratio NUMERIC(8, 6) NOT NULL,
    spectral_correlations JSONB NOT NULL,
    minimum_spectral_correlation NUMERIC(8, 6) NOT NULL,
    mean_spectral_correlation NUMERIC(8, 6) NOT NULL,
    spatial_detail_gain NUMERIC(10, 6) NOT NULL,
    output_crs VARCHAR(100) NOT NULL,
    output_resolution_x NUMERIC(16, 8) NOT NULL,
    output_resolution_y NUMERIC(16, 8) NOT NULL,
    raster_width INTEGER NOT NULL,
    raster_height INTEGER NOT NULL,
    band_count INTEGER NOT NULL,
    dtype VARCHAR(30) NOT NULL,
    output_uri VARCHAR(500) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    bounds_wgs84 JSONB NOT NULL,
    manifest JSONB NOT NULL,
    created_by VARCHAR(100) NOT NULL,
    created_by_code VARCHAR(50) NOT NULL,
    created_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_imagery_fusion_job UNIQUE (project_id, job_code),
    CONSTRAINT ck_imagery_fusion_assets_distinct CHECK (
        multispectral_asset_id <> panchromatic_asset_id
    ),
    CONSTRAINT ck_imagery_fusion_overlap CHECK (
        overlap_ratio > 0 AND overlap_ratio <= 1
    )
);

CREATE INDEX IF NOT EXISTS idx_imagery_fusion_project_created
    ON imagery_fusion_jobs (project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS imagery_fusion_events (
    id BIGSERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    job_id INTEGER NOT NULL REFERENCES imagery_fusion_jobs(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    actor_code VARCHAR(50) NOT NULL,
    actor_role VARCHAR(40) NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_imagery_fusion_event_job
    ON imagery_fusion_events (job_id, created_at DESC);
