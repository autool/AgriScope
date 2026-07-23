-- 多时相 NDVI 长势监测：保存实体来源、任务掩膜快照、分级成果、异常区和稳定用户审计。

CREATE TABLE IF NOT EXISTS growth_monitoring_runs (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    task_id INTEGER NOT NULL REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    run_code VARCHAR(80) NOT NULL,
    run_name VARCHAR(200) NOT NULL,
    baseline_asset_id INTEGER NOT NULL REFERENCES imagery_assets(id) ON DELETE RESTRICT,
    baseline_asset_code VARCHAR(80) NOT NULL,
    baseline_asset_name VARCHAR(200) NOT NULL,
    baseline_acquired_at TIMESTAMPTZ NOT NULL,
    baseline_step_id INTEGER NOT NULL REFERENCES imagery_processing_steps(id) ON DELETE RESTRICT,
    baseline_source_uri VARCHAR(500) NOT NULL,
    baseline_source_size_bytes BIGINT NOT NULL,
    baseline_source_sha256 VARCHAR(64) NOT NULL,
    current_asset_id INTEGER NOT NULL REFERENCES imagery_assets(id) ON DELETE RESTRICT,
    current_asset_code VARCHAR(80) NOT NULL,
    current_asset_name VARCHAR(200) NOT NULL,
    current_acquired_at TIMESTAMPTZ NOT NULL,
    current_step_id INTEGER NOT NULL REFERENCES imagery_processing_steps(id) ON DELETE RESTRICT,
    current_source_uri VARCHAR(500) NOT NULL,
    current_source_size_bytes BIGINT NOT NULL,
    current_source_sha256 VARCHAR(64) NOT NULL,
    poor_delta_threshold NUMERIC(7, 4) NOT NULL,
    good_delta_threshold NUMERIC(7, 4) NOT NULL,
    minimum_zone_area_ha NUMERIC(12, 4) NOT NULL,
    minimum_spatial_coverage_ratio NUMERIC(8, 6) NOT NULL,
    minimum_valid_pixel_ratio NUMERIC(8, 6) NOT NULL,
    algorithm_code VARCHAR(80) NOT NULL,
    algorithm_version VARCHAR(80) NOT NULL,
    task_plot_count INTEGER NOT NULL,
    task_updated_at TIMESTAMPTZ NOT NULL,
    output_crs VARCHAR(100) NOT NULL,
    output_resolution_x NUMERIC(16, 8) NOT NULL,
    output_resolution_y NUMERIC(16, 8) NOT NULL,
    raster_width INTEGER NOT NULL,
    raster_height INTEGER NOT NULL,
    bounds_wgs84 JSONB NOT NULL DEFAULT '[]'::jsonb,
    task_farmland_area_ha NUMERIC(18, 6) NOT NULL,
    common_footprint_farmland_area_ha NUMERIC(18, 6) NOT NULL,
    spatial_coverage_ratio NUMERIC(8, 6) NOT NULL,
    common_footprint_mask_pixel_count BIGINT NOT NULL,
    valid_pixel_count BIGINT NOT NULL,
    valid_pixel_ratio NUMERIC(8, 6) NOT NULL,
    poor_pixel_count BIGINT NOT NULL,
    normal_pixel_count BIGINT NOT NULL,
    good_pixel_count BIGINT NOT NULL,
    anomaly_zone_count INTEGER NOT NULL,
    anomaly_area_ha NUMERIC(16, 4) NOT NULL,
    classification_uri VARCHAR(500) NOT NULL,
    classification_filename VARCHAR(255) NOT NULL,
    classification_size_bytes BIGINT NOT NULL,
    classification_sha256 VARCHAR(64) NOT NULL,
    anomaly_uri VARCHAR(500) NOT NULL,
    anomaly_filename VARCHAR(255) NOT NULL,
    anomaly_size_bytes BIGINT NOT NULL,
    anomaly_sha256 VARCHAR(64) NOT NULL,
    manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by VARCHAR(100) NOT NULL,
    created_by_code VARCHAR(50) NOT NULL,
    created_by_role VARCHAR(40) NOT NULL,
    comment TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_growth_monitoring_run UNIQUE (project_id, run_code),
    CONSTRAINT ck_growth_monitoring_temporal_pair CHECK (
        baseline_asset_id <> current_asset_id
        AND baseline_acquired_at < current_acquired_at
    ),
    CONSTRAINT ck_growth_monitoring_thresholds CHECK (
        poor_delta_threshold >= -1 AND poor_delta_threshold < 0
        AND good_delta_threshold > 0 AND good_delta_threshold <= 1
        AND minimum_zone_area_ha > 0
        AND minimum_spatial_coverage_ratio > 0
        AND minimum_spatial_coverage_ratio <= 1
        AND minimum_valid_pixel_ratio > 0
        AND minimum_valid_pixel_ratio <= 1
    ),
    CONSTRAINT ck_growth_monitoring_counts CHECK (
        task_plot_count > 0
        AND raster_width > 0 AND raster_height > 0
        AND task_farmland_area_ha > 0
        AND common_footprint_farmland_area_ha > 0
        AND common_footprint_farmland_area_ha <= task_farmland_area_ha
        AND spatial_coverage_ratio > 0 AND spatial_coverage_ratio <= 1
        AND common_footprint_mask_pixel_count > 0
        AND valid_pixel_count > 0
        AND valid_pixel_count <= common_footprint_mask_pixel_count
        AND valid_pixel_ratio > 0 AND valid_pixel_ratio <= 1
        AND poor_pixel_count >= 0
        AND normal_pixel_count >= 0
        AND good_pixel_count >= 0
        AND poor_pixel_count + normal_pixel_count + good_pixel_count = valid_pixel_count
        AND anomaly_zone_count >= 0 AND anomaly_area_ha >= 0
    ),
    CONSTRAINT ck_growth_monitoring_artifacts CHECK (
        baseline_source_size_bytes > 0
        AND current_source_size_bytes > 0
        AND classification_size_bytes > 0
        AND anomaly_size_bytes > 0
        AND char_length(baseline_source_sha256) = 64
        AND char_length(current_source_sha256) = 64
        AND char_length(classification_sha256) = 64
        AND char_length(anomaly_sha256) = 64
    )
);

CREATE INDEX IF NOT EXISTS idx_growth_monitoring_runs_task_created
    ON growth_monitoring_runs (task_id, created_at DESC);

CREATE TABLE IF NOT EXISTS growth_monitoring_zones (
    id BIGSERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES growth_monitoring_runs(id) ON DELETE CASCADE,
    zone_code VARCHAR(100) NOT NULL,
    area_ha NUMERIC(16, 4) NOT NULL,
    baseline_ndvi_mean NUMERIC(8, 5) NOT NULL,
    current_ndvi_mean NUMERIC(8, 5) NOT NULL,
    ndvi_delta_mean NUMERIC(8, 5) NOT NULL,
    geom GEOMETRY(MULTIPOLYGON, 4326) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_growth_monitoring_zone UNIQUE (run_id, zone_code),
    CONSTRAINT ck_growth_monitoring_zone_values CHECK (
        area_ha > 0
        AND baseline_ndvi_mean BETWEEN -1 AND 1
        AND current_ndvi_mean BETWEEN -1 AND 1
        AND ndvi_delta_mean BETWEEN -2 AND 2
    )
);

CREATE INDEX IF NOT EXISTS idx_growth_monitoring_zones_run
    ON growth_monitoring_zones (run_id, area_ha DESC);
CREATE INDEX IF NOT EXISTS idx_growth_monitoring_zones_geom
    ON growth_monitoring_zones USING GIST (geom);

CREATE TABLE IF NOT EXISTS growth_monitoring_events (
    id BIGSERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    run_id INTEGER NOT NULL REFERENCES growth_monitoring_runs(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    actor_code VARCHAR(50) NOT NULL,
    actor_role VARCHAR(40) NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_growth_monitoring_events_run_created
    ON growth_monitoring_events (run_id, created_at);
