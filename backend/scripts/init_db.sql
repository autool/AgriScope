CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS farmland_plots (
    id SERIAL PRIMARY KEY,
    plot_code VARCHAR(50) NOT NULL UNIQUE,
    owner_village VARCHAR(100),
    area_ha NUMERIC(10, 4),
    geom GEOMETRY(POLYGON, 4326) NOT NULL
);

ALTER TABLE farmland_plots ADD COLUMN IF NOT EXISTS land_class VARCHAR(50);
ALTER TABLE farmland_plots ADD COLUMN IF NOT EXISTS crop_type VARCHAR(50);
ALTER TABLE farmland_plots ADD COLUMN IF NOT EXISTS planting_mode VARCHAR(50);
ALTER TABLE farmland_plots ADD COLUMN IF NOT EXISTS irrigation_condition VARCHAR(20);
ALTER TABLE farmland_plots ADD COLUMN IF NOT EXISTS source_name VARCHAR(120);
ALTER TABLE farmland_plots ADD COLUMN IF NOT EXISTS source_feature_id VARCHAR(80);
ALTER TABLE farmland_plots ADD COLUMN IF NOT EXISTS source_uri VARCHAR(500);
ALTER TABLE farmland_plots ADD COLUMN IF NOT EXISTS source_version VARCHAR(80);
ALTER TABLE farmland_plots ADD COLUMN IF NOT EXISTS source_updated_at TIMESTAMPTZ;
ALTER TABLE farmland_plots ADD COLUMN IF NOT EXISTS province_name VARCHAR(100);
ALTER TABLE farmland_plots ADD COLUMN IF NOT EXISTS city_name VARCHAR(100);
ALTER TABLE farmland_plots ADD COLUMN IF NOT EXISTS district_name VARCHAR(100);
ALTER TABLE farmland_plots ADD COLUMN IF NOT EXISTS district_code VARCHAR(50);
ALTER TABLE farmland_plots ADD COLUMN IF NOT EXISTS interpretation_status VARCHAR(30) NOT NULL DEFAULT 'interpreting';
ALTER TABLE farmland_plots ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE farmland_plots ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_farmland_plots_geom
    ON farmland_plots USING GIST (geom);

CREATE UNIQUE INDEX IF NOT EXISTS idx_farmland_plots_source_feature
    ON farmland_plots (source_name, source_feature_id)
    WHERE source_name IS NOT NULL AND source_feature_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS monitoring_projects (
    id SERIAL PRIMARY KEY,
    project_code VARCHAR(50) NOT NULL UNIQUE,
    project_name VARCHAR(200) NOT NULL,
    province VARCHAR(100) NOT NULL,
    monitor_year INTEGER NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    progress NUMERIC(5, 2) NOT NULL DEFAULT 0,
    deadline DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS project_users (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL
        REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    user_code VARCHAR(50) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    role_code VARCHAR(40) NOT NULL,
    role_name VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_project_user_code UNIQUE (project_id, user_code),
    CONSTRAINT ck_project_user_status CHECK (status IN ('active', 'disabled'))
);

CREATE INDEX IF NOT EXISTS idx_project_users_project_role
    ON project_users (project_id, role_code, status);

CREATE TABLE IF NOT EXISTS project_rule_configs (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL UNIQUE
        REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    field_offset_threshold_m NUMERIC(8, 2) NOT NULL DEFAULT 5.00,
    field_search_radius_m NUMERIC(10, 2) NOT NULL DEFAULT 1000.00,
    positional_accuracy_pixels NUMERIC(6, 2) NOT NULL DEFAULT 2.00,
    max_capture_image_days INTEGER NOT NULL DEFAULT 15,
    updated_by VARCHAR(100) NOT NULL DEFAULT '系统默认配置',
    updated_by_code VARCHAR(50),
    updated_by_role VARCHAR(40),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_rule_offset_positive CHECK (field_offset_threshold_m > 0),
    CONSTRAINT ck_rule_search_radius CHECK (
        field_search_radius_m > field_offset_threshold_m
    ),
    CONSTRAINT ck_rule_pixels_positive CHECK (positional_accuracy_pixels > 0),
    CONSTRAINT ck_rule_days_positive CHECK (max_capture_image_days > 0)
);

CREATE TABLE IF NOT EXISTS project_rule_config_audits (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL
        REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    operator VARCHAR(100) NOT NULL,
    operator_code VARCHAR(50),
    operator_role VARCHAR(40),
    previous_values JSONB NOT NULL,
    new_values JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rule_config_audits_project_time
    ON project_rule_config_audits (project_id, created_at DESC);

ALTER TABLE project_rule_configs
    ADD COLUMN IF NOT EXISTS updated_by_code VARCHAR(50);
ALTER TABLE project_rule_configs
    ADD COLUMN IF NOT EXISTS updated_by_role VARCHAR(40);
ALTER TABLE project_rule_config_audits
    ADD COLUMN IF NOT EXISTS operator_code VARCHAR(50);
ALTER TABLE project_rule_config_audits
    ADD COLUMN IF NOT EXISTS operator_role VARCHAR(40);

CREATE TABLE IF NOT EXISTS monitoring_tasks (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    task_code VARCHAR(50) NOT NULL UNIQUE,
    task_name VARCHAR(200) NOT NULL,
    administrative_region VARCHAR(150) NOT NULL,
    assignee VARCHAR(100),
    status VARCHAR(30) NOT NULL DEFAULT 'interpreting',
    total_plots INTEGER NOT NULL DEFAULT 0,
    completed_plots INTEGER NOT NULL DEFAULT 0,
    quality_score NUMERIC(5, 2),
    deadline DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS task_plots (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL
        REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    plot_code VARCHAR(50) NOT NULL
        REFERENCES farmland_plots(plot_code) ON DELETE CASCADE,
    assigned_by VARCHAR(100) NOT NULL,
    assigned_by_code VARCHAR(50),
    assigned_by_role VARCHAR(40),
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_task_plot UNIQUE (task_id, plot_code)
);

CREATE INDEX IF NOT EXISTS idx_task_plots_task
    ON task_plots (task_id);

CREATE INDEX IF NOT EXISTS idx_task_plots_plot
    ON task_plots (plot_code);

ALTER TABLE task_plots ADD COLUMN IF NOT EXISTS assigned_by_code VARCHAR(50);
ALTER TABLE task_plots ADD COLUMN IF NOT EXISTS assigned_by_role VARCHAR(40);

CREATE TABLE IF NOT EXISTS imagery_assets (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    asset_code VARCHAR(80) NOT NULL UNIQUE,
    asset_name VARCHAR(200) NOT NULL,
    sensor_type VARCHAR(80) NOT NULL,
    acquired_at TIMESTAMPTZ NOT NULL,
    cloud_cover NUMERIC(5, 2),
    resolution_m NUMERIC(8, 2),
    processing_level VARCHAR(30),
    data_status VARCHAR(20) NOT NULL DEFAULT 'operational',
    calibration_status VARCHAR(30) NOT NULL DEFAULT 'pending',
    correction_status VARCHAR(30) NOT NULL DEFAULT 'pending',
    original_filename VARCHAR(255),
    file_uri VARCHAR(500),
    file_format VARCHAR(30),
    file_size_bytes BIGINT,
    checksum_sha256 VARCHAR(64),
    band_count INTEGER,
    raster_width INTEGER,
    raster_height INTEGER,
    crs VARCHAR(100),
    raster_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    imported_by VARCHAR(100),
    spatial_extent GEOMETRY(POLYGON, 4326),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_imagery_assets_extent
    ON imagery_assets USING GIST (spatial_extent);

ALTER TABLE imagery_assets ADD COLUMN IF NOT EXISTS original_filename VARCHAR(255);
ALTER TABLE imagery_assets
    ADD COLUMN IF NOT EXISTS data_status VARCHAR(20) NOT NULL DEFAULT 'operational';
ALTER TABLE imagery_assets ADD COLUMN IF NOT EXISTS file_uri VARCHAR(500);
ALTER TABLE imagery_assets ADD COLUMN IF NOT EXISTS file_format VARCHAR(30);
ALTER TABLE imagery_assets ADD COLUMN IF NOT EXISTS file_size_bytes BIGINT;
ALTER TABLE imagery_assets ADD COLUMN IF NOT EXISTS checksum_sha256 VARCHAR(64);
ALTER TABLE imagery_assets ADD COLUMN IF NOT EXISTS band_count INTEGER;
ALTER TABLE imagery_assets ADD COLUMN IF NOT EXISTS raster_width INTEGER;
ALTER TABLE imagery_assets ADD COLUMN IF NOT EXISTS raster_height INTEGER;
ALTER TABLE imagery_assets ADD COLUMN IF NOT EXISTS crs VARCHAR(100);
ALTER TABLE imagery_assets
    ADD COLUMN IF NOT EXISTS raster_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE imagery_assets ADD COLUMN IF NOT EXISTS imported_by VARCHAR(100);

CREATE UNIQUE INDEX IF NOT EXISTS idx_imagery_assets_checksum
    ON imagery_assets (checksum_sha256)
    WHERE checksum_sha256 IS NOT NULL;

CREATE TABLE IF NOT EXISTS quality_issues (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    plot_code VARCHAR(50) REFERENCES farmland_plots(plot_code) ON DELETE CASCADE,
    rule_code VARCHAR(60) NOT NULL,
    issue_type VARCHAR(30) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    description VARCHAR(500) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    source VARCHAR(20) NOT NULL DEFAULT 'auto',
    assignee VARCHAR(100),
    resolved_by VARCHAR(100),
    resolved_by_code VARCHAR(50),
    resolved_by_role VARCHAR(40),
    resolution_comment VARCHAR(1000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_quality_issues_task_status
    ON quality_issues (task_id, status);

ALTER TABLE quality_issues ADD COLUMN IF NOT EXISTS assignee VARCHAR(100);
ALTER TABLE quality_issues ADD COLUMN IF NOT EXISTS resolved_by VARCHAR(100);
ALTER TABLE quality_issues ADD COLUMN IF NOT EXISTS resolved_by_code VARCHAR(50);
ALTER TABLE quality_issues ADD COLUMN IF NOT EXISTS resolved_by_role VARCHAR(40);
ALTER TABLE quality_issues ADD COLUMN IF NOT EXISTS resolution_comment VARCHAR(1000);

CREATE TABLE IF NOT EXISTS plot_quality_checks (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    plot_code VARCHAR(50) NOT NULL REFERENCES farmland_plots(plot_code) ON DELETE CASCADE,
    plot_version INTEGER NOT NULL,
    score NUMERIC(5, 2) NOT NULL,
    can_submit BOOLEAN NOT NULL,
    rules JSONB NOT NULL DEFAULT '[]'::jsonb,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_plot_quality_check UNIQUE (task_id, plot_code)
);

CREATE INDEX IF NOT EXISTS idx_plot_quality_checks_task_gate
    ON plot_quality_checks (task_id, can_submit);

CREATE TABLE IF NOT EXISTS review_records (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    review_level VARCHAR(30) NOT NULL,
    action VARCHAR(30) NOT NULL,
    reviewer VARCHAR(100) NOT NULL,
    reviewer_code VARCHAR(50),
    reviewer_role VARCHAR(40),
    comment VARCHAR(1000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE review_records ADD COLUMN IF NOT EXISTS reviewer_code VARCHAR(50);
ALTER TABLE review_records ADD COLUMN IF NOT EXISTS reviewer_role VARCHAR(40);

CREATE TABLE IF NOT EXISTS field_verifications (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    verification_code VARCHAR(60) NOT NULL UNIQUE,
    investigator VARCHAR(100) NOT NULL,
    investigator_code VARCHAR(50),
    location GEOMETRY(POINT, 4326) NOT NULL,
    observed_land_class VARCHAR(50),
    observed_crop_type VARCHAR(50),
    photo_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
    voice_url VARCHAR(500),
    remark VARCHAR(1000),
    captured_at TIMESTAMPTZ NOT NULL,
    source_name VARCHAR(120),
    source_uri VARCHAR(500),
    source_version VARCHAR(80),
    source_record_id VARCHAR(100),
    source_checksum_sha256 VARCHAR(64),
    import_batch_code VARCHAR(80),
    imported_by VARCHAR(100),
    imported_by_code VARCHAR(50),
    imported_by_role VARCHAR(40),
    matched_plot_code VARCHAR(50) REFERENCES farmland_plots(plot_code),
    offset_distance_m NUMERIC(10, 2),
    match_status VARCHAR(30) NOT NULL DEFAULT 'pending',
    resolution_status VARCHAR(30) NOT NULL DEFAULT 'pending',
    resolution_decision VARCHAR(30),
    resolution_comment VARCHAR(1000),
    resolved_by VARCHAR(100),
    resolved_by_code VARCHAR(50),
    resolved_by_role VARCHAR(40),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_field_verifications_location
    ON field_verifications USING GIST (location);

CREATE INDEX IF NOT EXISTS idx_field_verifications_task_status
    ON field_verifications (task_id, match_status, resolution_status);

ALTER TABLE field_verifications
    ADD COLUMN IF NOT EXISTS investigator_code VARCHAR(50);
ALTER TABLE field_verifications
    ADD COLUMN IF NOT EXISTS resolved_by VARCHAR(100);
ALTER TABLE field_verifications
    ADD COLUMN IF NOT EXISTS resolved_by_code VARCHAR(50);
ALTER TABLE field_verifications
    ADD COLUMN IF NOT EXISTS resolved_by_role VARCHAR(40);
ALTER TABLE field_verifications ADD COLUMN IF NOT EXISTS source_name VARCHAR(120);
ALTER TABLE field_verifications ADD COLUMN IF NOT EXISTS source_uri VARCHAR(500);
ALTER TABLE field_verifications ADD COLUMN IF NOT EXISTS source_version VARCHAR(80);
ALTER TABLE field_verifications ADD COLUMN IF NOT EXISTS source_record_id VARCHAR(100);
ALTER TABLE field_verifications ADD COLUMN IF NOT EXISTS source_checksum_sha256 VARCHAR(64);
ALTER TABLE field_verifications ADD COLUMN IF NOT EXISTS import_batch_code VARCHAR(80);
ALTER TABLE field_verifications ADD COLUMN IF NOT EXISTS imported_by VARCHAR(100);
ALTER TABLE field_verifications ADD COLUMN IF NOT EXISTS imported_by_code VARCHAR(50);
ALTER TABLE field_verifications ADD COLUMN IF NOT EXISTS imported_by_role VARCHAR(40);

CREATE UNIQUE INDEX IF NOT EXISTS idx_field_verifications_source_record
    ON field_verifications (task_id, source_name, source_record_id)
    WHERE source_record_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS plot_versions (
    id SERIAL PRIMARY KEY,
    plot_code VARCHAR(50) NOT NULL REFERENCES farmland_plots(plot_code) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    land_class VARCHAR(50),
    crop_type VARCHAR(50),
    planting_mode VARCHAR(50),
    irrigation_condition VARCHAR(20),
    interpretation_status VARCHAR(30) NOT NULL,
    geom GEOMETRY(POLYGON, 4326) NOT NULL,
    change_summary VARCHAR(500),
    created_by VARCHAR(100) NOT NULL,
    created_by_code VARCHAR(50),
    created_by_role VARCHAR(40),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (plot_code, version)
);

CREATE INDEX IF NOT EXISTS idx_plot_versions_geom
    ON plot_versions USING GIST (geom);

ALTER TABLE plot_versions ADD COLUMN IF NOT EXISTS created_by_code VARCHAR(50);
ALTER TABLE plot_versions ADD COLUMN IF NOT EXISTS created_by_role VARCHAR(40);

CREATE TABLE IF NOT EXISTS plot_edit_operations (
    id SERIAL PRIMARY KEY,
    operation_code VARCHAR(80) NOT NULL UNIQUE,
    task_id INTEGER NOT NULL
        REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    operation_type VARCHAR(30) NOT NULL,
    source_plot_codes JSONB NOT NULL,
    result_plot_codes JSONB NOT NULL,
    applied_versions JSONB NOT NULL DEFAULT '{}'::jsonb,
    reverted_versions JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(20) NOT NULL DEFAULT 'applied',
    operator VARCHAR(100) NOT NULL,
    operator_code VARCHAR(50) NOT NULL,
    operator_role VARCHAR(40) NOT NULL,
    comment VARCHAR(500) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reverted_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_plot_edit_operations_task_created
    ON plot_edit_operations (task_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_plot_edit_operations_source_codes
    ON plot_edit_operations USING GIN (source_plot_codes);

CREATE INDEX IF NOT EXISTS idx_plot_edit_operations_result_codes
    ON plot_edit_operations USING GIN (result_plot_codes);

CREATE TABLE IF NOT EXISTS plot_edit_operation_events (
    id SERIAL PRIMARY KEY,
    event_code VARCHAR(80) NOT NULL UNIQUE,
    operation_id INTEGER NOT NULL
        REFERENCES plot_edit_operations(id) ON DELETE CASCADE,
    action VARCHAR(20) NOT NULL,
    operator VARCHAR(100) NOT NULL,
    operator_code VARCHAR(50) NOT NULL,
    operator_role VARCHAR(40) NOT NULL,
    comment VARCHAR(500) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_plot_edit_operation_events_operation
    ON plot_edit_operation_events (operation_id, created_at DESC);

CREATE TABLE IF NOT EXISTS area_statistics_import_batches (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL
        REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    batch_code VARCHAR(80) NOT NULL UNIQUE,
    source_name VARCHAR(120) NOT NULL,
    source_uri VARCHAR(500) NOT NULL,
    source_version VARCHAR(80) NOT NULL,
    source_checksum_sha256 VARCHAR(64) NOT NULL,
    conflict_strategy VARCHAR(20) NOT NULL,
    row_count INTEGER NOT NULL,
    snapshot_payload JSON NOT NULL DEFAULT '[]'::json,
    imported_by VARCHAR(100) NOT NULL,
    imported_by_code VARCHAR(50) NOT NULL,
    imported_by_role VARCHAR(40) NOT NULL,
    import_comment VARCHAR(500) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_area_statistics_import_project_created
    ON area_statistics_import_batches (project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS area_statistics_snapshots (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    monitor_year INTEGER NOT NULL,
    total_area_ha NUMERIC(14, 4) NOT NULL,
    farmland_area_ha NUMERIC(14, 4) NOT NULL,
    crop_area_ha NUMERIC(14, 4) NOT NULL,
    import_batch_id INTEGER,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, monitor_year),
    CONSTRAINT fk_area_statistics_snapshot_import_batch
        FOREIGN KEY (import_batch_id)
        REFERENCES area_statistics_import_batches(id)
        ON DELETE SET NULL
);

ALTER TABLE area_statistics_snapshots
    ADD COLUMN IF NOT EXISTS import_batch_id INTEGER;
ALTER TABLE area_statistics_snapshots
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_area_statistics_snapshot_import_batch'
    ) THEN
        ALTER TABLE area_statistics_snapshots
            ADD CONSTRAINT fk_area_statistics_snapshot_import_batch
            FOREIGN KEY (import_batch_id)
            REFERENCES area_statistics_import_batches(id)
            ON DELETE SET NULL;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS disaster_patches (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    patch_code VARCHAR(60) NOT NULL UNIQUE,
    disaster_type VARCHAR(30) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    affected_area_ha NUMERIC(12, 4) NOT NULL,
    crop_type VARCHAR(50),
    detected_at DATE NOT NULL,
    ndvi_change NUMERIC(6, 3),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    source VARCHAR(120) NOT NULL,
    source_uri VARCHAR(500),
    source_version VARCHAR(80),
    source_feature_id VARCHAR(100),
    source_checksum_sha256 VARCHAR(64),
    import_batch_code VARCHAR(80),
    imported_by VARCHAR(100),
    imported_by_code VARCHAR(50),
    imported_by_role VARCHAR(40),
    reviewed_by VARCHAR(100),
    reviewed_by_code VARCHAR(50),
    reviewed_by_role VARCHAR(40),
    review_comment VARCHAR(1000),
    reviewed_at TIMESTAMPTZ,
    geom GEOMETRY(POLYGON, 4326) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_disaster_patches_geom
    ON disaster_patches USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_disaster_patches_task_severity
    ON disaster_patches (task_id, severity, status);

ALTER TABLE disaster_patches ADD COLUMN IF NOT EXISTS reviewed_by VARCHAR(100);
ALTER TABLE disaster_patches ADD COLUMN IF NOT EXISTS reviewed_by_code VARCHAR(50);
ALTER TABLE disaster_patches ADD COLUMN IF NOT EXISTS reviewed_by_role VARCHAR(40);
ALTER TABLE disaster_patches ADD COLUMN IF NOT EXISTS review_comment VARCHAR(1000);
ALTER TABLE disaster_patches ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;
ALTER TABLE disaster_patches ALTER COLUMN source TYPE VARCHAR(120);
ALTER TABLE disaster_patches ADD COLUMN IF NOT EXISTS source_uri VARCHAR(500);
ALTER TABLE disaster_patches ADD COLUMN IF NOT EXISTS source_version VARCHAR(80);
ALTER TABLE disaster_patches ADD COLUMN IF NOT EXISTS source_feature_id VARCHAR(100);
ALTER TABLE disaster_patches ADD COLUMN IF NOT EXISTS source_checksum_sha256 VARCHAR(64);
ALTER TABLE disaster_patches ADD COLUMN IF NOT EXISTS import_batch_code VARCHAR(80);
ALTER TABLE disaster_patches ADD COLUMN IF NOT EXISTS imported_by VARCHAR(100);
ALTER TABLE disaster_patches ADD COLUMN IF NOT EXISTS imported_by_code VARCHAR(50);
ALTER TABLE disaster_patches ADD COLUMN IF NOT EXISTS imported_by_role VARCHAR(40);

CREATE UNIQUE INDEX IF NOT EXISTS idx_disaster_patches_source_feature
    ON disaster_patches (task_id, source, source_feature_id)
    WHERE source_feature_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS imagery_processing_steps (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES imagery_assets(id) ON DELETE CASCADE,
    step_code VARCHAR(50) NOT NULL,
    step_name VARCHAR(100) NOT NULL,
    sequence INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    progress INTEGER NOT NULL DEFAULT 0,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_uri VARCHAR(500),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (asset_id, step_code)
);

CREATE TABLE IF NOT EXISTS delivery_packages (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    package_code VARCHAR(80) NOT NULL UNIQUE,
    package_name VARCHAR(200) NOT NULL,
    version INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'generating',
    generated_by VARCHAR(100) NOT NULL,
    generated_by_code VARCHAR(50),
    generated_by_role VARCHAR(40),
    file_uri VARCHAR(500),
    file_size_bytes INTEGER,
    checksum_sha256 VARCHAR(64),
    manifest JSONB NOT NULL DEFAULT '[]'::jsonb,
    quality_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

ALTER TABLE delivery_packages
    ADD COLUMN IF NOT EXISTS generated_by_code VARCHAR(50);
ALTER TABLE delivery_packages
    ADD COLUMN IF NOT EXISTS generated_by_role VARCHAR(40);

CREATE INDEX IF NOT EXISTS idx_delivery_packages_task_version
    ON delivery_packages (task_id, version DESC);

CREATE TABLE IF NOT EXISTS administrative_boundaries (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    boundary_code VARCHAR(50) NOT NULL UNIQUE,
    boundary_name VARCHAR(100) NOT NULL,
    boundary_level VARCHAR(20) NOT NULL,
    parent_code VARCHAR(50),
    geom GEOMETRY(MULTIPOLYGON, 4326) NOT NULL,
    source_name VARCHAR(120) NOT NULL,
    source_uri VARCHAR(500),
    source_version VARCHAR(80),
    source_updated_at DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 兼容已经使用旧演示表结构初始化的开发数据库。
ALTER TABLE administrative_boundaries
    ADD COLUMN IF NOT EXISTS source_name VARCHAR(120);
ALTER TABLE administrative_boundaries
    ADD COLUMN IF NOT EXISTS parent_code VARCHAR(50);
ALTER TABLE administrative_boundaries
    ADD COLUMN IF NOT EXISTS source_uri VARCHAR(500);
ALTER TABLE administrative_boundaries
    ADD COLUMN IF NOT EXISTS source_version VARCHAR(80);
ALTER TABLE administrative_boundaries
    ADD COLUMN IF NOT EXISTS source_updated_at DATE;
ALTER TABLE administrative_boundaries
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
UPDATE administrative_boundaries
SET source_name = '未标注历史数据'
WHERE source_name IS NULL;
ALTER TABLE administrative_boundaries
    ALTER COLUMN source_name SET NOT NULL;
ALTER TABLE administrative_boundaries
    ALTER COLUMN geom TYPE GEOMETRY(MULTIPOLYGON, 4326)
    USING ST_Multi(geom);

CREATE INDEX IF NOT EXISTS idx_administrative_boundaries_geom
    ON administrative_boundaries USING GIST (geom);

INSERT INTO monitoring_projects (
    project_code, project_name, province, monitor_year, status, progress, deadline
) VALUES (
    'RS-2026', '2026 年省级农作物种植监测', '黑龙江省', 2026, 'active', 0, '2026-08-08'
) ON CONFLICT (project_code) DO UPDATE SET
    project_name = EXCLUDED.project_name,
    progress = 0,
    deadline = EXCLUDED.deadline,
    updated_at = NOW();

INSERT INTO project_users (
    project_id, user_code, display_name, role_code, role_name,
    status, is_default
)
SELECT project.id, seed.user_code, seed.display_name, seed.role_code,
       seed.role_name, 'active', seed.is_default
FROM monitoring_projects AS project
CROSS JOIN (
    VALUES
        ('interp-li-jing', '李静', 'interpreter', '内业解译员', TRUE),
        ('field-zhang-qiang', '张强', 'field_inspector', '外业核查员', FALSE),
        ('quality-wang-haifeng', '王海峰', 'quality_inspector', '质检员', FALSE),
        ('manager-zhao-zhiyuan', '赵志远', 'project_manager', '项目负责人', FALSE),
        ('client-agri-dept', '农业农村厅审核代表', 'client_reviewer', '甲方（监管方）', FALSE)
) AS seed(user_code, display_name, role_code, role_name, is_default)
WHERE project.project_code = 'RS-2026'
ON CONFLICT (project_id, user_code) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    role_code = EXCLUDED.role_code,
    role_name = EXCLUDED.role_name,
    status = EXCLUDED.status,
    is_default = EXCLUDED.is_default,
    updated_at = NOW();

UPDATE review_records AS record
SET reviewer_code = project_user.user_code,
    reviewer_role = project_user.role_code
FROM monitoring_tasks AS task
JOIN project_users AS project_user
  ON project_user.project_id = task.project_id
WHERE record.task_id = task.id
  AND project_user.display_name = record.reviewer
  AND record.reviewer_code IS NULL;

INSERT INTO project_rule_configs (
    project_id, field_offset_threshold_m, field_search_radius_m,
    positional_accuracy_pixels, max_capture_image_days, updated_by
)
SELECT id, 5.00, 1000.00, 2.00, 15, '系统默认配置'
FROM monitoring_projects
WHERE project_code = 'RS-2026'
ON CONFLICT (project_id) DO NOTHING;

INSERT INTO monitoring_tasks (
    project_id, task_code, task_name, administrative_region, assignee,
    status, total_plots, completed_plots, quality_score, deadline
)
SELECT id, 'RS-2026-045', '黑龙江省全域分级耕地解译作业单元',
       '黑龙江省（13 个地级区域、122 个县区全量行政层级）', '李静',
       'interpreting', 0, 0, NULL, '2026-07-28'
FROM monitoring_projects WHERE project_code = 'RS-2026'
ON CONFLICT (task_code) DO UPDATE SET
    task_name = '黑龙江省全域分级耕地解译作业单元',
    administrative_region = '黑龙江省（13 个地级区域、122 个县区全量行政层级）',
    total_plots = EXCLUDED.total_plots,
    completed_plots = EXCLUDED.completed_plots,
    quality_score = EXCLUDED.quality_score,
    updated_at = NOW();

-- 年度面积趋势不得使用固定演示数值。当前年度由任务图斑实时聚合，
-- 历史年度仅在导入真实统计快照后展示。

-- 灾害模型结果必须通过 /api/v1/disasters/import-geojson 导入真实 GeoJSON；
-- 初始化阶段不再生成无来源实体文件的规则矩形演示斑块。

-- 影像资产必须通过上传接口读取实体栅格元数据并创建处理流水线；
-- 初始化脚本不得写入无文件、无校验和的“业务影像”占位记录。

-- 使用版本化快照覆盖为黑龙江省全域省/市/县区三级真实行政区划。
-- 快照通过 docker-compose 只读挂载，初始化过程不依赖外部网络。
DELETE FROM administrative_boundaries
WHERE project_id IN (
    SELECT id FROM monitoring_projects WHERE project_code = 'RS-2026'
);

WITH snapshot AS (
    SELECT pg_read_file(
        '/docker-entrypoint-initdb.d/data/administrative_boundaries/'
        'heilongjiang_areas_v3_20260721.geojson'
    )::jsonb AS payload
), boundary_features AS (
    SELECT
        jsonb_array_elements(payload -> 'features') AS feature,
        payload -> 'metadata' AS metadata
    FROM snapshot
)
INSERT INTO administrative_boundaries (
    project_id, boundary_code, boundary_name, boundary_level, parent_code,
    geom, source_name, source_uri, source_version, source_updated_at
)
SELECT
    project.id,
    feature -> 'properties' ->> 'adcode',
    feature -> 'properties' ->> 'name',
    feature -> 'properties' ->> 'level',
    feature -> 'properties' -> 'parent' ->> 'adcode',
    ST_Multi(
        ST_CollectionExtract(
            ST_MakeValid(
                ST_SetSRID(
                    ST_GeomFromGeoJSON((feature -> 'geometry')::text),
                    4326
                )
            ),
            3
        )
    ),
    metadata ->> 'source_name',
    metadata ->> 'source_uri',
    metadata ->> 'source_version',
    (metadata ->> 'source_updated_at')::date
FROM boundary_features
CROSS JOIN monitoring_projects AS project
WHERE project.project_code = 'RS-2026';

-- 使用版本化 OSM 快照替换旧版 5 条手绘规则矩形。
-- 数据仅用于系统联调，保留 OSM way/relation ID、版本、更新时间和原始链接，
-- 不将开放地图众包边界表述为法定基本农田成果。
UPDATE field_verifications
SET matched_plot_code = NULL,
    offset_distance_m = NULL,
    match_status = 'pending',
    updated_at = NOW()
WHERE matched_plot_code IN ('HLJ-001', 'HLJ-002', 'HLJ-003', 'HLJ-004', 'HLJ-005');

DELETE FROM farmland_plots
WHERE plot_code IN ('HLJ-001', 'HLJ-002', 'HLJ-003', 'HLJ-004', 'HLJ-005');

UPDATE field_verifications
SET matched_plot_code = NULL,
    offset_distance_m = NULL,
    match_status = 'pending',
    updated_at = NOW()
WHERE matched_plot_code LIKE 'OSM-HRB-%';

DELETE FROM farmland_plots
WHERE plot_code LIKE 'OSM-HRB-%'
  AND source_name = 'OpenStreetMap';

WITH farmland_snapshot AS (
    SELECT pg_read_file(
        '/docker-entrypoint-initdb.d/data/farmland/'
        'osm_heilongjiang_farmland_20260722.geojson'
    )::jsonb AS payload
), farmland_features AS (
    SELECT jsonb_array_elements(payload -> 'features') AS feature
    FROM farmland_snapshot
), candidates AS (
    SELECT
        feature,
        COALESCE(
            feature -> 'properties' ->> 'source_feature_id',
            'way/' || (feature -> 'properties' ->> 'osm_way_id')
        ) AS source_feature_id,
        ST_SetSRID(
            ST_GeomFromGeoJSON((feature -> 'geometry')::text),
            4326
        ) AS geom
    FROM farmland_features
)
INSERT INTO farmland_plots (
    plot_code, owner_village, area_ha, geom, land_class, crop_type,
    planting_mode, irrigation_condition, interpretation_status, version,
    source_name, source_feature_id, source_uri, source_version,
    source_updated_at, province_name, city_name, district_name,
    district_code, updated_at
)
SELECT
    'OSM-HLJ-' || CASE
        WHEN candidate.source_feature_id LIKE 'way/%'
            THEN REPLACE(candidate.source_feature_id, 'way/', '')
        ELSE REPLACE(
            REPLACE(candidate.source_feature_id, 'relation/', 'R'),
            '#part/', '-P'
        )
    END,
    district.boundary_name || '（OSM未标注村名）',
    ROUND((ST_Area(candidate.geom::geography) / 10000.0)::numeric, 4),
    candidate.geom,
    CASE candidate.feature -> 'properties' ->> 'landuse'
        WHEN 'farmland' THEN '耕地'
        WHEN 'greenhouse_horticulture' THEN '耕地'
        WHEN 'allotments' THEN '耕地'
        WHEN 'orchard' THEN '园地'
        WHEN 'plant_nursery' THEN '园地'
        WHEN 'vineyard' THEN '园地'
        WHEN 'forest' THEN '林地'
        WHEN 'meadow' THEN '草地'
        WHEN 'grass' THEN '草地'
        WHEN 'reservoir' THEN '水域'
        WHEN 'basin' THEN '水域'
        WHEN 'residential' THEN '建设用地'
        WHEN 'commercial' THEN '建设用地'
        WHEN 'industrial' THEN '建设用地'
        WHEN 'construction' THEN '建设用地'
        WHEN 'farmyard' THEN '建设用地'
    END,
    NULL, NULL, NULL, 'interpreting', 1,
    candidate.feature -> 'properties' ->> 'source_name',
    candidate.source_feature_id,
    candidate.feature -> 'properties' ->> 'source_uri',
    candidate.feature -> 'properties' ->> 'osm_version',
    (candidate.feature -> 'properties' ->> 'osm_timestamp')::timestamptz,
    '黑龙江省',
    city.boundary_name,
    district.boundary_name,
    district.boundary_code,
    NOW()
FROM candidates AS candidate
JOIN LATERAL (
    SELECT boundary.boundary_code, boundary.boundary_name, boundary.parent_code
    FROM administrative_boundaries AS boundary
    WHERE boundary.boundary_level = 'district'
      AND ST_Covers(boundary.geom, ST_PointOnSurface(candidate.geom))
    ORDER BY ST_Area(boundary.geom::geography)
    LIMIT 1
) AS district ON TRUE
JOIN administrative_boundaries AS city
  ON city.boundary_code = district.parent_code
WHERE ST_IsValid(candidate.geom)
  AND ST_Area(candidate.geom::geography) > 0
  AND candidate.feature -> 'properties' ->> 'landuse' IN (
      'farmland', 'greenhouse_horticulture', 'orchard',
      'plant_nursery', 'meadow', 'allotments', 'vineyard',
      'forest', 'grass', 'reservoir', 'basin', 'residential',
      'commercial', 'industrial', 'construction', 'farmyard'
  )
ON CONFLICT (plot_code) DO NOTHING;

INSERT INTO task_plots (
    task_id, plot_code, assigned_by, assigned_by_code, assigned_by_role
)
SELECT task.id, plot.plot_code, 'OpenStreetMap 数据导入程序',
       'system_osm_import', 'system'
FROM monitoring_tasks AS task
JOIN farmland_plots AS plot
  ON plot.interpretation_status != 'deleted'
WHERE task.task_code = 'RS-2026-045'
ON CONFLICT (task_id, plot_code) DO NOTHING;

UPDATE monitoring_tasks
SET task_name = '黑龙江省全域分级耕地解译作业单元',
    administrative_region = CONCAT(
        '黑龙江省（13 个地级区域、122 个县区全量层级；OSM 地块覆盖 ',
        (SELECT COUNT(DISTINCT city_name) FROM farmland_plots
         WHERE interpretation_status != 'deleted'),
        ' 个地级区域 ',
        (SELECT COUNT(DISTINCT district_code) FROM farmland_plots
         WHERE interpretation_status != 'deleted'),
        ' 县区）'
    ),
    status = 'interpreting',
    total_plots = (
        SELECT COUNT(*)
        FROM task_plots AS scope
        JOIN farmland_plots AS plot ON plot.plot_code = scope.plot_code
        WHERE scope.task_id = monitoring_tasks.id
          AND plot.interpretation_status != 'deleted'
    ),
    completed_plots = (
        SELECT COUNT(*)
        FROM task_plots AS scope
        JOIN farmland_plots AS plot ON plot.plot_code = scope.plot_code
        WHERE scope.task_id = monitoring_tasks.id
          AND plot.interpretation_status = 'interpreted'
    ),
    quality_score = NULL,
    updated_at = NOW()
WHERE task_code = 'RS-2026-045';

INSERT INTO review_records (
    task_id, review_level, action, reviewer,
    reviewer_code, reviewer_role, comment, created_at
)
SELECT id, 'interpretation', 'plot_source_imported', 'OpenStreetMap 数据导入程序',
       'system_osm_import', 'system',
       CONCAT(
           '同步 ',
           (SELECT COUNT(*) FROM farmland_plots
            WHERE interpretation_status != 'deleted'),
           ' 条可追溯 OpenStreetMap 农业地块边界，覆盖 ',
           (SELECT COUNT(DISTINCT city_name) FROM farmland_plots
            WHERE interpretation_status != 'deleted'),
           ' 个地级区域 ',
           (SELECT COUNT(DISTINCT district_code) FROM farmland_plots
            WHERE interpretation_status != 'deleted'),
           ' 县区'
       ),
       NOW()
FROM monitoring_tasks WHERE task_code = 'RS-2026-045'
AND NOT EXISTS (
    SELECT 1 FROM review_records
    WHERE task_id = monitoring_tasks.id AND action = 'plot_source_imported'
);

INSERT INTO plot_versions (
    plot_code, version, land_class, crop_type, planting_mode,
    irrigation_condition, interpretation_status, geom, change_summary,
    created_by, created_by_code, created_by_role
)
SELECT plot_code, 1, land_class, crop_type, planting_mode,
       irrigation_condition, interpretation_status, geom, '初始基线版本',
       '系统初始化', 'system_init', 'system'
FROM farmland_plots
ON CONFLICT (plot_code, version) DO NOTHING;

INSERT INTO plot_versions (
    plot_code, version, land_class, crop_type, planting_mode,
    irrigation_condition, interpretation_status, geom, change_summary,
    created_by, created_by_code, created_by_role
)
SELECT plot_code, version, land_class, crop_type, planting_mode,
       irrigation_condition, interpretation_status, geom, '初始化图斑版本',
       '系统初始化', 'system_init', 'system'
FROM farmland_plots
ON CONFLICT (plot_code, version) DO NOTHING;

-- 外业记录必须通过单条采集接口或 /api/v1/field-verifications/import-csv
-- 导入真实 GPS 和现场媒体引用；初始化阶段不再生成虚构点位。
+-- 2026-07-22：新增多源数据目录、生产批次、县区作业包和采购量化规则。
-- 本迁移仅创建生产底座，不写入虚构生产批次、资产或完成状态。

ALTER TABLE project_rule_configs
    ADD COLUMN IF NOT EXISTS construction_min_area_sqm
        NUMERIC(10, 2) NOT NULL DEFAULT 200.00;
ALTER TABLE project_rule_configs
    ADD COLUMN IF NOT EXISTS other_agricultural_min_area_sqm
        NUMERIC(10, 2) NOT NULL DEFAULT 400.00;
ALTER TABLE project_rule_configs
    ADD COLUMN IF NOT EXISTS completeness_rate_min
        NUMERIC(5, 2) NOT NULL DEFAULT 98.00;
ALTER TABLE project_rule_configs
    ADD COLUMN IF NOT EXISTS boundary_agreement_rate_min
        NUMERIC(5, 2) NOT NULL DEFAULT 90.00;
ALTER TABLE project_rule_configs
    ADD COLUMN IF NOT EXISTS land_class_accuracy_min
        NUMERIC(5, 2) NOT NULL DEFAULT 90.00;
ALTER TABLE project_rule_configs
    ADD COLUMN IF NOT EXISTS key_field_accuracy_min
        NUMERIC(5, 2) NOT NULL DEFAULT 95.00;
ALTER TABLE project_rule_configs
    ADD COLUMN IF NOT EXISTS max_cloud_cover_percent NUMERIC(5, 2);
ALTER TABLE project_rule_configs
    ADD COLUMN IF NOT EXISTS output_crs
        VARCHAR(100) NOT NULL DEFAULT 'EPSG:4490';
ALTER TABLE project_rule_configs
    ADD COLUMN IF NOT EXISTS output_projection
        VARCHAR(200) NOT NULL
        DEFAULT 'CGCS2000 高斯-克吕格（按成果分幅配置中央经线）';
ALTER TABLE project_rule_configs
    ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

CREATE TABLE IF NOT EXISTS dataset_assets (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL
        REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    task_id INTEGER REFERENCES monitoring_tasks(id) ON DELETE SET NULL,
    asset_code VARCHAR(80) NOT NULL UNIQUE,
    asset_name VARCHAR(200) NOT NULL,
    asset_type VARCHAR(30) NOT NULL,
    source_name VARCHAR(120) NOT NULL,
    source_uri VARCHAR(500) NOT NULL,
    source_version VARCHAR(80) NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    crs VARCHAR(100),
    extent GEOMETRY(POLYGON, 4326),
    time_start TIMESTAMPTZ,
    time_end TIMESTAMPTZ,
    security_classification VARCHAR(30) NOT NULL,
    data_status VARCHAR(20) NOT NULL DEFAULT 'operational',
    verification_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    registered_by VARCHAR(100) NOT NULL,
    registered_by_code VARCHAR(50) NOT NULL,
    registered_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_dataset_asset_type CHECK (
        asset_type IN (
            'imagery', 'vector', 'table', 'dem', 'control', 'weather',
            'management', 'uav', 'iot'
        )
    ),
    CONSTRAINT ck_dataset_security CHECK (
        security_classification IN (
            'public', 'internal', 'restricted', 'confidential'
        )
    ),
    CONSTRAINT ck_dataset_data_status CHECK (
        data_status IN ('operational', 'demo')
    ),
    CONSTRAINT ck_dataset_verification CHECK (
        verification_status IN ('pending', 'verified', 'rejected', 'unavailable')
    ),
    CONSTRAINT ck_dataset_time_range CHECK (
        time_end IS NULL OR time_start IS NULL OR time_end >= time_start
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_dataset_assets_project_checksum
    ON dataset_assets (project_id, checksum_sha256);
CREATE INDEX IF NOT EXISTS idx_dataset_assets_project_type
    ON dataset_assets (project_id, asset_type, verification_status);
CREATE INDEX IF NOT EXISTS idx_dataset_assets_extent
    ON dataset_assets USING GIST (extent);

CREATE TABLE IF NOT EXISTS dataset_lineages (
    id SERIAL PRIMARY KEY,
    parent_asset_id INTEGER NOT NULL
        REFERENCES dataset_assets(id) ON DELETE CASCADE,
    derived_asset_id INTEGER NOT NULL
        REFERENCES dataset_assets(id) ON DELETE CASCADE,
    relation_type VARCHAR(40) NOT NULL,
    process_code VARCHAR(80),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_dataset_lineage_relation UNIQUE (
        parent_asset_id, derived_asset_id, relation_type
    ),
    CONSTRAINT ck_dataset_lineage_no_self CHECK (
        parent_asset_id != derived_asset_id
    )
);

CREATE INDEX IF NOT EXISTS idx_dataset_lineages_derived
    ON dataset_lineages (derived_asset_id);

CREATE TABLE IF NOT EXISTS production_batches (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL
        REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    task_id INTEGER NOT NULL
        REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    batch_code VARCHAR(80) NOT NULL UNIQUE,
    batch_name VARCHAR(200) NOT NULL,
    source_asset_id INTEGER REFERENCES dataset_assets(id) ON DELETE RESTRICT,
    target_asset_id INTEGER REFERENCES dataset_assets(id) ON DELETE RESTRICT,
    rule_config_version INTEGER NOT NULL,
    rule_profile_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    planned_start_date DATE NOT NULL,
    planned_end_date DATE NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'draft',
    created_by VARCHAR(100) NOT NULL,
    created_by_code VARCHAR(50) NOT NULL,
    created_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_production_batch_dates CHECK (
        planned_end_date >= planned_start_date
    ),
    CONSTRAINT ck_production_batch_status CHECK (
        status IN (
            'draft', 'planned', 'in_progress', 'reconciling',
            'completed', 'cancelled'
        )
    ),
    CONSTRAINT ck_production_batch_assets CHECK (
        source_asset_id IS NULL OR target_asset_id IS NULL
        OR source_asset_id != target_asset_id
    )
);

CREATE INDEX IF NOT EXISTS idx_production_batches_task_status
    ON production_batches (task_id, status, planned_end_date);

CREATE TABLE IF NOT EXISTS work_packages (
    id SERIAL PRIMARY KEY,
    batch_id INTEGER NOT NULL
        REFERENCES production_batches(id) ON DELETE CASCADE,
    package_code VARCHAR(100) NOT NULL UNIQUE,
    package_name VARCHAR(200) NOT NULL,
    region_code VARCHAR(50) NOT NULL,
    region_name VARCHAR(100) NOT NULL,
    region_level VARCHAR(20) NOT NULL,
    planned_area_ha NUMERIC(16, 4) NOT NULL,
    planned_plot_count INTEGER NOT NULL,
    assignee_code VARCHAR(50) NOT NULL,
    assignee_name VARCHAR(100) NOT NULL,
    deadline DATE NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    reconciliation_status VARCHAR(30) NOT NULL DEFAULT 'pending',
    delivery_status VARCHAR(30) NOT NULL DEFAULT 'pending',
    created_by VARCHAR(100) NOT NULL,
    created_by_code VARCHAR(50) NOT NULL,
    created_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_work_package_region UNIQUE (batch_id, region_code),
    CONSTRAINT ck_work_package_scope CHECK (
        planned_area_ha > 0 AND planned_plot_count > 0
    ),
    CONSTRAINT ck_work_package_status CHECK (
        status IN ('pending', 'in_progress', 'blocked', 'completed')
    ),
    CONSTRAINT ck_work_package_reconciliation CHECK (
        reconciliation_status IN ('pending', 'checking', 'passed', 'conflict')
    ),
    CONSTRAINT ck_work_package_delivery CHECK (
        delivery_status IN ('pending', 'submitted', 'accepted', 'returned')
    )
);

CREATE INDEX IF NOT EXISTS idx_work_packages_batch_status
    ON work_packages (batch_id, status, deadline);
CREATE INDEX IF NOT EXISTS idx_work_packages_assignee
    ON work_packages (assignee_code, status);

CREATE TABLE IF NOT EXISTS work_package_plots (
    id SERIAL PRIMARY KEY,
    work_package_id INTEGER NOT NULL
        REFERENCES work_packages(id) ON DELETE CASCADE,
    plot_code VARCHAR(50) NOT NULL
        REFERENCES farmland_plots(plot_code) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_work_package_plot UNIQUE (work_package_id, plot_code)
);

CREATE INDEX IF NOT EXISTS idx_work_package_plots_plot
    ON work_package_plots (plot_code);

CREATE TABLE IF NOT EXISTS production_audit_events (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL
        REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    task_id INTEGER REFERENCES monitoring_tasks(id) ON DELETE SET NULL,
    entity_type VARCHAR(30) NOT NULL,
    entity_code VARCHAR(100) NOT NULL,
    action VARCHAR(40) NOT NULL,
    previous_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    new_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    operator VARCHAR(100) NOT NULL,
    operator_code VARCHAR(50) NOT NULL,
    operator_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_production_audit_entity_time
    ON production_audit_events (
        project_id, entity_type, entity_code, created_at DESC
    );

INSERT INTO project_users (
    project_id, user_code, display_name, role_code, role_name,
    status, is_default
)
SELECT id, 'supervisor-independent', '独立监理单位代表',
       'independent_supervisor', '独立监理', 'active', FALSE
FROM monitoring_projects
WHERE project_code = 'RS-2026'
ON CONFLICT (project_id, user_code) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    role_code = EXCLUDED.role_code,
    role_name = EXCLUDED.role_name,
    status = EXCLUDED.status,
    is_default = EXCLUDED.is_default,
    updated_at = NOW();
