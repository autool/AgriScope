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
ALTER TABLE farmland_plots ADD COLUMN IF NOT EXISTS custom_attributes JSONB NOT NULL DEFAULT '{}'::jsonb;
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

-- 自定义字段编码在项目内稳定且不可变；字段语义变更递增版本并写入审计。
CREATE TABLE IF NOT EXISTS project_plot_attribute_fields (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL
        REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    field_code VARCHAR(40) NOT NULL,
    label VARCHAR(100) NOT NULL,
    field_type VARCHAR(20) NOT NULL,
    required BOOLEAN NOT NULL DEFAULT FALSE,
    options JSONB NOT NULL DEFAULT '[]'::jsonb,
    display_order INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    version INTEGER NOT NULL DEFAULT 1,
    created_by VARCHAR(100) NOT NULL,
    created_by_code VARCHAR(50) NOT NULL,
    created_by_role VARCHAR(40) NOT NULL,
    updated_by VARCHAR(100) NOT NULL,
    updated_by_code VARCHAR(50) NOT NULL,
    updated_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_project_plot_attribute_field_code
        UNIQUE (project_id, field_code),
    CONSTRAINT ck_project_plot_attribute_field_type
        CHECK (field_type IN ('text', 'number', 'date', 'boolean', 'single_select')),
    CONSTRAINT ck_project_plot_attribute_field_status
        CHECK (status IN ('active', 'inactive')),
    CONSTRAINT ck_project_plot_attribute_field_order
        CHECK (display_order BETWEEN 0 AND 9999),
    CONSTRAINT ck_project_plot_attribute_field_version CHECK (version >= 1),
    CONSTRAINT ck_project_plot_attribute_field_options CHECK (
        (field_type = 'single_select' AND jsonb_array_length(options) > 0)
        OR (field_type != 'single_select' AND options = '[]'::jsonb)
    )
);

CREATE INDEX IF NOT EXISTS idx_project_plot_attribute_fields_project_order
    ON project_plot_attribute_fields (project_id, status, display_order, id);

CREATE TABLE IF NOT EXISTS project_plot_attribute_field_audits (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL
        REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    field_id INTEGER NOT NULL
        REFERENCES project_plot_attribute_fields(id) ON DELETE CASCADE,
    action VARCHAR(20) NOT NULL,
    previous_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    new_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    operator VARCHAR(100) NOT NULL,
    operator_code VARCHAR(50) NOT NULL,
    operator_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_project_plot_attribute_field_audit_action
        CHECK (action IN ('created', 'updated'))
);

CREATE INDEX IF NOT EXISTS idx_project_plot_attribute_field_audits_time
    ON project_plot_attribute_field_audits (
        project_id,
        field_id,
        created_at DESC
    );

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

-- 影像批量入库按 1–20 个文件原子提交；保存批次清单 SHA256、逐文件实体证据
-- 和稳定用户角色，任一成员失败时不得留下资产记录或已发布文件。
CREATE TABLE IF NOT EXISTS imagery_import_batches (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL
        REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    task_id INTEGER NOT NULL
        REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    batch_code VARCHAR(90) NOT NULL UNIQUE,
    item_count INTEGER NOT NULL,
    total_size_bytes BIGINT NOT NULL,
    manifest_sha256 VARCHAR(64) NOT NULL,
    manifest_payload JSONB NOT NULL,
    imported_by VARCHAR(100) NOT NULL,
    imported_by_code VARCHAR(50) NOT NULL,
    imported_by_role VARCHAR(40) NOT NULL,
    import_comment TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_imagery_import_batch_values CHECK (
        item_count BETWEEN 1 AND 20
        AND total_size_bytes > 0
        AND manifest_sha256 ~ '^[0-9a-f]{64}$'
        AND char_length(trim(import_comment)) >= 10
    )
);

CREATE INDEX IF NOT EXISTS idx_imagery_import_batches_project_created
    ON imagery_import_batches (project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS imagery_import_batch_items (
    id BIGSERIAL PRIMARY KEY,
    batch_id INTEGER NOT NULL
        REFERENCES imagery_import_batches(id) ON DELETE CASCADE,
    asset_id INTEGER NOT NULL
        REFERENCES imagery_assets(id) ON DELETE RESTRICT,
    sequence INTEGER NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_imagery_import_batch_item_sequence
        UNIQUE (batch_id, sequence),
    CONSTRAINT uq_imagery_import_batch_item_asset
        UNIQUE (batch_id, asset_id),
    CONSTRAINT ck_imagery_import_batch_item_values CHECK (
        sequence BETWEEN 1 AND 20
        AND file_size_bytes > 0
        AND checksum_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE INDEX IF NOT EXISTS idx_imagery_import_batch_items_batch
    ON imagery_import_batch_items (batch_id, sequence);

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

CREATE TABLE IF NOT EXISTS task_quality_runs (
    id SERIAL PRIMARY KEY,
    run_code VARCHAR(80) NOT NULL UNIQUE,
    task_id INTEGER NOT NULL REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    task_plot_count INTEGER NOT NULL,
    task_updated_at_snapshot TIMESTAMPTZ NOT NULL,
    rule_config_version INTEGER NOT NULL,
    rule_config_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    imagery_snapshot_digest VARCHAR(64) NOT NULL,
    imagery_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    custom_field_schema_digest VARCHAR(64) NOT NULL,
    custom_field_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
    checked_plot_count INTEGER NOT NULL,
    passing_plot_count INTEGER NOT NULL,
    failed_plot_count INTEGER NOT NULL,
    average_score NUMERIC(5, 2),
    issue_count INTEGER NOT NULL,
    can_submit BOOLEAN NOT NULL,
    duration_ms INTEGER NOT NULL,
    rule_summaries JSONB NOT NULL DEFAULT '[]'::jsonb,
    operator VARCHAR(100) NOT NULL,
    operator_code VARCHAR(50) NOT NULL,
    operator_role VARCHAR(40) NOT NULL,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_task_quality_run_non_negative CHECK (
        task_plot_count >= 0
        AND checked_plot_count >= 0
        AND passing_plot_count >= 0
        AND failed_plot_count >= 0
        AND issue_count >= 0
        AND duration_ms >= 0
    ),
    CONSTRAINT ck_task_quality_run_checked_balance CHECK (
        checked_plot_count = passing_plot_count + failed_plot_count
    ),
    CONSTRAINT ck_task_quality_run_full_coverage CHECK (
        task_plot_count = checked_plot_count
    ),
    CONSTRAINT ck_task_quality_run_rule_version CHECK (
        rule_config_version >= 1
    ),
    CONSTRAINT ck_task_quality_run_schema_digest CHECK (
        char_length(custom_field_schema_digest) = 64
    ),
    CONSTRAINT ck_task_quality_run_imagery_digest CHECK (
        char_length(imagery_snapshot_digest) = 64
    )
);

CREATE INDEX IF NOT EXISTS idx_task_quality_runs_task_created
    ON task_quality_runs (task_id, created_at DESC);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_task_quality_run_full_coverage'
    ) THEN
        ALTER TABLE task_quality_runs
            ADD CONSTRAINT ck_task_quality_run_full_coverage
            CHECK (task_plot_count = checked_plot_count);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_task_quality_run_rule_version'
    ) THEN
        ALTER TABLE task_quality_runs
            ADD CONSTRAINT ck_task_quality_run_rule_version
            CHECK (rule_config_version >= 1);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_task_quality_run_imagery_digest'
    ) THEN
        ALTER TABLE task_quality_runs
            ADD CONSTRAINT ck_task_quality_run_imagery_digest
            CHECK (char_length(imagery_snapshot_digest) = 64);
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS review_records (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    review_level VARCHAR(30) NOT NULL,
    action VARCHAR(30) NOT NULL,
    reviewer VARCHAR(100) NOT NULL,
    reviewer_code VARCHAR(50),
    reviewer_role VARCHAR(40),
    quality_run_code VARCHAR(80)
        CONSTRAINT fk_review_records_quality_run_code
        REFERENCES task_quality_runs(run_code) ON DELETE RESTRICT,
    comment VARCHAR(1000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE review_records ADD COLUMN IF NOT EXISTS reviewer_code VARCHAR(50);
ALTER TABLE review_records ADD COLUMN IF NOT EXISTS reviewer_role VARCHAR(40);
ALTER TABLE review_records ADD COLUMN IF NOT EXISTS quality_run_code VARCHAR(80);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_review_records_quality_run_code'
    ) THEN
        ALTER TABLE review_records
            ADD CONSTRAINT fk_review_records_quality_run_code
            FOREIGN KEY (quality_run_code)
            REFERENCES task_quality_runs(run_code)
            ON DELETE RESTRICT;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_review_records_quality_run
    ON review_records (quality_run_code);

CREATE TABLE IF NOT EXISTS field_verifications (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    verification_code VARCHAR(60) NOT NULL UNIQUE,
    investigator VARCHAR(100) NOT NULL,
    investigator_code VARCHAR(50),
    location GEOMETRY(POINT, 4326) NOT NULL,
    location_accuracy_m NUMERIC(10, 2),
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
    source_file_uri VARCHAR(500),
    source_file_size_bytes BIGINT,
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
    ADD COLUMN IF NOT EXISTS location_accuracy_m NUMERIC(10, 2);
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
ALTER TABLE field_verifications ADD COLUMN IF NOT EXISTS source_file_uri VARCHAR(500);
ALTER TABLE field_verifications ADD COLUMN IF NOT EXISTS source_file_size_bytes BIGINT;
ALTER TABLE field_verifications ADD COLUMN IF NOT EXISTS import_batch_code VARCHAR(80);
ALTER TABLE field_verifications ADD COLUMN IF NOT EXISTS imported_by VARCHAR(100);
ALTER TABLE field_verifications ADD COLUMN IF NOT EXISTS imported_by_code VARCHAR(50);
ALTER TABLE field_verifications ADD COLUMN IF NOT EXISTS imported_by_role VARCHAR(40);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_field_verification_location_accuracy'
    ) THEN
        ALTER TABLE field_verifications
            ADD CONSTRAINT ck_field_verification_location_accuracy
            CHECK (
                location_accuracy_m IS NULL
                OR (location_accuracy_m > 0 AND location_accuracy_m <= 10000)
            );
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_field_verification_source_file_size'
    ) THEN
        ALTER TABLE field_verifications
            ADD CONSTRAINT ck_field_verification_source_file_size
            CHECK (
                source_file_size_bytes IS NULL
                OR source_file_size_bytes > 0
            );
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_field_verifications_source_record
    ON field_verifications (task_id, source_name, source_record_id)
    WHERE source_record_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS field_verification_artifacts (
    id SERIAL PRIMARY KEY,
    field_verification_id INTEGER NOT NULL
        REFERENCES field_verifications(id) ON DELETE CASCADE,
    artifact_code VARCHAR(80) NOT NULL UNIQUE,
    artifact_type VARCHAR(20) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    media_type VARCHAR(100) NOT NULL,
    file_uri VARCHAR(500) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    description TEXT NOT NULL,
    uploaded_by VARCHAR(100) NOT NULL,
    uploaded_by_code VARCHAR(50) NOT NULL,
    uploaded_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_field_verification_artifact_checksum
        UNIQUE (field_verification_id, checksum_sha256),
    CONSTRAINT ck_field_verification_artifact_type
        CHECK (artifact_type IN ('photo', 'voice', 'form')),
    CONSTRAINT ck_field_verification_artifact_size
        CHECK (file_size_bytes > 0),
    CONSTRAINT ck_field_verification_artifact_checksum
        CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS idx_field_verification_artifacts_record_type
    ON field_verification_artifacts (field_verification_id, artifact_type);

CREATE TABLE IF NOT EXISTS field_verification_artifact_events (
    id SERIAL PRIMARY KEY,
    field_verification_id INTEGER NOT NULL
        REFERENCES field_verifications(id) ON DELETE CASCADE,
    artifact_id INTEGER
        REFERENCES field_verification_artifacts(id) ON DELETE SET NULL,
    event_type VARCHAR(20) NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    actor VARCHAR(100) NOT NULL,
    actor_code VARCHAR(50) NOT NULL,
    actor_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_field_verification_artifact_event_type
        CHECK (event_type IN ('uploaded', 'downloaded'))
);

CREATE INDEX IF NOT EXISTS idx_field_verification_artifact_events_record_time
    ON field_verification_artifact_events (
        field_verification_id,
        created_at DESC
    );

CREATE TABLE IF NOT EXISTS plot_versions (
    id SERIAL PRIMARY KEY,
    plot_code VARCHAR(50) NOT NULL REFERENCES farmland_plots(plot_code) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    owner_village VARCHAR(100),
    land_class VARCHAR(50),
    crop_type VARCHAR(50),
    planting_mode VARCHAR(50),
    irrigation_condition VARCHAR(20),
    custom_attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
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
ALTER TABLE plot_versions ADD COLUMN IF NOT EXISTS owner_village VARCHAR(100);
ALTER TABLE plot_versions ADD COLUMN IF NOT EXISTS custom_attributes JSONB NOT NULL DEFAULT '{}'::jsonb;

-- 地块属性 Excel 每次导入保存原始工作簿实体、SHA256、逐行结果和稳定用户角色；
-- 任一行校验失败时数据库事务与新建文件同时回滚。
CREATE TABLE IF NOT EXISTS plot_attribute_import_batches (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL
        REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    batch_code VARCHAR(90) NOT NULL UNIQUE,
    original_filename VARCHAR(255) NOT NULL,
    file_uri VARCHAR(500) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    definition_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
    definition_digest VARCHAR(64) NOT NULL,
    row_count INTEGER NOT NULL,
    changed_count INTEGER NOT NULL,
    unchanged_count INTEGER NOT NULL,
    imported_by VARCHAR(100) NOT NULL,
    imported_by_code VARCHAR(50) NOT NULL,
    imported_by_role VARCHAR(40) NOT NULL,
    import_comment TEXT NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_plot_attribute_import_row_count
        CHECK (row_count BETWEEN 1 AND 500),
    CONSTRAINT ck_plot_attribute_import_result_counts
        CHECK (
            changed_count >= 0
            AND unchanged_count >= 0
            AND changed_count + unchanged_count = row_count
        ),
    CONSTRAINT ck_plot_attribute_import_file_size
        CHECK (file_size_bytes > 0),
    CONSTRAINT ck_plot_attribute_import_checksum
        CHECK (char_length(checksum_sha256) = 64),
    CONSTRAINT ck_plot_attribute_import_definition_digest
        CHECK (char_length(definition_digest) = 64)
);

CREATE INDEX IF NOT EXISTS idx_plot_attribute_import_batches_task_time
    ON plot_attribute_import_batches (task_id, imported_at DESC);

ALTER TABLE plot_attribute_import_batches
    ADD COLUMN IF NOT EXISTS definition_snapshot JSONB NOT NULL
    DEFAULT '[]'::jsonb;
ALTER TABLE plot_attribute_import_batches
    ADD COLUMN IF NOT EXISTS definition_digest VARCHAR(64);
UPDATE plot_attribute_import_batches
SET definition_digest = '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'
WHERE definition_digest IS NULL;
ALTER TABLE plot_attribute_import_batches
    ALTER COLUMN definition_digest SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_plot_attribute_import_definition_digest'
    ) THEN
        ALTER TABLE plot_attribute_import_batches
            ADD CONSTRAINT ck_plot_attribute_import_definition_digest
            CHECK (char_length(definition_digest) = 64);
    END IF;
END
$$;

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

-- 面积统计正式成果由服务端生成 XLSX、PDF、manifest 并原子封装为 ZIP；
-- 保存任务与历史快照状态，用于后续数据变化时识别历史版本。
CREATE TABLE IF NOT EXISTS statistics_reports (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    report_code VARCHAR(100) NOT NULL UNIQUE,
    report_title VARCHAR(200) NOT NULL,
    version INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    bundle_uri VARCHAR(500) NOT NULL,
    bundle_size_bytes BIGINT NOT NULL,
    bundle_checksum_sha256 VARCHAR(64) NOT NULL,
    xlsx_size_bytes BIGINT NOT NULL,
    xlsx_checksum_sha256 VARCHAR(64) NOT NULL,
    pdf_size_bytes BIGINT NOT NULL,
    pdf_checksum_sha256 VARCHAR(64) NOT NULL,
    task_plot_count INTEGER NOT NULL,
    task_updated_at_snapshot TIMESTAMPTZ NOT NULL,
    history_snapshot_count INTEGER NOT NULL,
    history_latest_updated_at TIMESTAMPTZ,
    report_manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
    generation_comment TEXT NOT NULL,
    generated_by VARCHAR(100) NOT NULL,
    generated_by_code VARCHAR(50) NOT NULL,
    generated_by_role VARCHAR(40) NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_statistics_report_task_version UNIQUE (task_id, version),
    CONSTRAINT ck_statistics_report_status CHECK (
        status IN ('completed', 'superseded', 'invalid')
    ),
    CONSTRAINT ck_statistics_report_file_sizes CHECK (
        bundle_size_bytes > 0
        AND xlsx_size_bytes > 0
        AND pdf_size_bytes > 0
    ),
    CONSTRAINT ck_statistics_report_checksums CHECK (
        char_length(bundle_checksum_sha256) = 64
        AND char_length(xlsx_checksum_sha256) = 64
        AND char_length(pdf_checksum_sha256) = 64
    ),
    CONSTRAINT ck_statistics_report_source_counts CHECK (
        task_plot_count >= 0 AND history_snapshot_count >= 0
    )
);

CREATE INDEX IF NOT EXISTS idx_statistics_reports_task_version
    ON statistics_reports (task_id, version DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_statistics_reports_current_task
    ON statistics_reports (task_id)
    WHERE status = 'completed';

-- 任务作用域矢量成果支持真实 GeoJSON、Shapefile、KML 和 OpenFileGDB；
-- 每次导出保存格式、筛选、任务版本、逐文件 manifest 和稳定用户审计。
CREATE TABLE IF NOT EXISTS vector_export_packages (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    export_code VARCHAR(100) NOT NULL UNIQUE,
    export_title VARCHAR(200) NOT NULL,
    version INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    formats JSONB NOT NULL DEFAULT '[]'::jsonb,
    district_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    land_classes JSONB NOT NULL DEFAULT '[]'::jsonb,
    feature_count INTEGER NOT NULL,
    task_plot_count INTEGER NOT NULL,
    task_updated_at_snapshot TIMESTAMPTZ NOT NULL,
    file_uri VARCHAR(500) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    export_manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
    generation_comment TEXT NOT NULL,
    generated_by VARCHAR(100) NOT NULL,
    generated_by_code VARCHAR(50) NOT NULL,
    generated_by_role VARCHAR(40) NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_vector_export_task_version UNIQUE (task_id, version),
    CONSTRAINT ck_vector_export_status CHECK (
        status IN ('completed', 'superseded', 'invalid')
    ),
    CONSTRAINT ck_vector_export_file_evidence CHECK (
        file_size_bytes > 0 AND char_length(checksum_sha256) = 64
    ),
    CONSTRAINT ck_vector_export_counts CHECK (
        feature_count >= 0 AND task_plot_count >= 0
    )
);

CREATE INDEX IF NOT EXISTS idx_vector_export_task_version
    ON vector_export_packages (task_id, version DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_vector_export_current_task
    ON vector_export_packages (task_id)
    WHERE status = 'completed';

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

CREATE TABLE IF NOT EXISTS disaster_reports (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    report_code VARCHAR(100) NOT NULL,
    report_title VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL,
    file_uri VARCHAR(500) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    source_patch_count INTEGER NOT NULL,
    source_confirmed_count INTEGER NOT NULL,
    source_excluded_count INTEGER NOT NULL,
    source_latest_updated_at TIMESTAMPTZ NOT NULL,
    affected_area_ha NUMERIC(14, 4) NOT NULL,
    report_manifest JSONB NOT NULL,
    generation_comment TEXT NOT NULL,
    generated_by VARCHAR(100) NOT NULL,
    generated_by_code VARCHAR(50) NOT NULL,
    generated_by_role VARCHAR(40) NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_disaster_report_code UNIQUE (report_code),
    CONSTRAINT ck_disaster_report_status
        CHECK (status IN ('completed', 'superseded', 'invalid')),
    CONSTRAINT ck_disaster_report_file_evidence
        CHECK (file_size_bytes > 0 AND char_length(checksum_sha256) = 64),
    CONSTRAINT ck_disaster_report_source_counts
        CHECK (
            source_patch_count >= 0
            AND source_confirmed_count >= 0
            AND source_excluded_count >= 0
        )
);

CREATE INDEX IF NOT EXISTS idx_disaster_reports_task_generated
    ON disaster_reports (task_id, generated_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_disaster_reports_current_task
    ON disaster_reports (task_id)
    WHERE status = 'completed';

CREATE TABLE IF NOT EXISTS imagery_processing_steps (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES imagery_assets(id) ON DELETE CASCADE,
    step_code VARCHAR(50) NOT NULL,
    step_name VARCHAR(100) NOT NULL,
    sequence INTEGER NOT NULL,
    is_required BOOLEAN NOT NULL DEFAULT TRUE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    progress INTEGER NOT NULL DEFAULT 0,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_uri VARCHAR(500),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (asset_id, step_code)
);

ALTER TABLE imagery_processing_steps
    ADD COLUMN IF NOT EXISTS is_required BOOLEAN NOT NULL DEFAULT TRUE;

UPDATE imagery_processing_steps
SET sequence = 6
WHERE step_code = 'band_products'
  AND sequence = 5;

INSERT INTO imagery_processing_steps (
    asset_id,
    step_code,
    step_name,
    sequence,
    is_required,
    status,
    progress,
    parameters
)
SELECT
    asset.id,
    'enhancement',
    '影像增强',
    5,
    FALSE,
    'pending',
    0,
    '{"method": "optional"}'::jsonb
FROM imagery_assets AS asset
WHERE NOT EXISTS (
    SELECT 1
    FROM imagery_processing_steps AS step
    WHERE step.asset_id = asset.id
      AND step.step_code = 'enhancement'
);

-- 两期已校验 NDVI 产品在任务耕地图斑范围内执行长势分级，
-- 保存分类 GeoTIFF、异常区 GeoJSON、PostGIS 面积和稳定用户审计。
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

-- 成果验收正式报告绑定当前有效成果包，服务端生成 DOCX、PDF、manifest；
-- 保存任务、成果包、质量摘要和稳定用户角色快照，防止旧报告冒充当前验收材料。
CREATE TABLE IF NOT EXISTS acceptance_reports (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    delivery_package_id INTEGER NOT NULL
        REFERENCES delivery_packages(id) ON DELETE RESTRICT,
    report_code VARCHAR(110) NOT NULL UNIQUE,
    report_title VARCHAR(200) NOT NULL,
    version INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    bundle_uri VARCHAR(500) NOT NULL,
    bundle_size_bytes BIGINT NOT NULL,
    bundle_checksum_sha256 VARCHAR(64) NOT NULL,
    docx_filename VARCHAR(160) NOT NULL,
    docx_size_bytes BIGINT NOT NULL,
    docx_checksum_sha256 VARCHAR(64) NOT NULL,
    pdf_filename VARCHAR(160) NOT NULL,
    pdf_size_bytes BIGINT NOT NULL,
    pdf_checksum_sha256 VARCHAR(64) NOT NULL,
    task_plot_count INTEGER NOT NULL,
    task_updated_at_snapshot TIMESTAMPTZ NOT NULL,
    delivery_package_code VARCHAR(80) NOT NULL,
    delivery_package_completed_at_snapshot TIMESTAMPTZ NOT NULL,
    delivery_package_size_bytes BIGINT NOT NULL,
    delivery_package_checksum_sha256 VARCHAR(64) NOT NULL,
    delivery_manifest_count INTEGER NOT NULL,
    quality_summary_checksum_sha256 VARCHAR(64) NOT NULL,
    report_manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
    generation_comment TEXT NOT NULL,
    generated_by VARCHAR(100) NOT NULL,
    generated_by_code VARCHAR(50) NOT NULL,
    generated_by_role VARCHAR(40) NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_acceptance_report_task_version UNIQUE (task_id, version),
    CONSTRAINT ck_acceptance_report_status CHECK (
        status IN ('completed', 'superseded', 'invalid')
    ),
    CONSTRAINT ck_acceptance_report_file_sizes CHECK (
        bundle_size_bytes > 0
        AND docx_size_bytes > 0
        AND pdf_size_bytes > 0
    ),
    CONSTRAINT ck_acceptance_report_checksums CHECK (
        char_length(bundle_checksum_sha256) = 64
        AND char_length(docx_checksum_sha256) = 64
        AND char_length(pdf_checksum_sha256) = 64
        AND char_length(delivery_package_checksum_sha256) = 64
        AND char_length(quality_summary_checksum_sha256) = 64
    ),
    CONSTRAINT ck_acceptance_report_source_counts CHECK (
        task_plot_count >= 0 AND delivery_manifest_count >= 0
    )
);

CREATE INDEX IF NOT EXISTS idx_acceptance_reports_task_version
    ON acceptance_reports (task_id, version DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_acceptance_reports_current_task
    ON acceptance_reports (task_id)
    WHERE status = 'completed';

-- 源栅格离线介质封存：把当前交付包、业务源影像、完成处理产物和已验证
-- 多源数据实体重新校验后写入可独立解压的 ZIP64 分卷，并保存顶层规范清单。
CREATE TABLE IF NOT EXISTS offline_archives (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL
        REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    delivery_package_id INTEGER NOT NULL
        REFERENCES delivery_packages(id) ON DELETE RESTRICT,
    archive_code VARCHAR(100) NOT NULL,
    archive_name VARCHAR(200) NOT NULL,
    version INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    volume_capacity_bytes BIGINT NOT NULL,
    volume_count INTEGER NOT NULL,
    source_count INTEGER NOT NULL,
    total_source_bytes BIGINT NOT NULL,
    total_archive_bytes BIGINT NOT NULL,
    source_snapshot_sha256 VARCHAR(64) NOT NULL,
    canonical_manifest JSONB NOT NULL,
    manifest_uri VARCHAR(500) NOT NULL,
    manifest_size_bytes BIGINT NOT NULL,
    manifest_checksum_sha256 VARCHAR(64) NOT NULL,
    delivery_package_code VARCHAR(80) NOT NULL,
    delivery_package_completed_at_snapshot TIMESTAMPTZ NOT NULL,
    delivery_package_size_bytes BIGINT NOT NULL,
    delivery_package_checksum_sha256 VARCHAR(64) NOT NULL,
    generated_by VARCHAR(100) NOT NULL,
    generated_by_code VARCHAR(50) NOT NULL,
    generated_by_role VARCHAR(40) NOT NULL,
    generation_comment TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    superseded_at TIMESTAMPTZ,
    CONSTRAINT uq_offline_archive_code UNIQUE (archive_code),
    CONSTRAINT uq_offline_archive_task_version UNIQUE (task_id, version),
    CONSTRAINT ck_offline_archive_status CHECK (
        status IN ('completed', 'superseded', 'invalid')
    ),
    CONSTRAINT ck_offline_archive_counts CHECK (
        volume_capacity_bytes >= 67108864
        AND volume_count > 0
        AND source_count > 0
        AND total_source_bytes > 0
        AND total_archive_bytes > 0
    ),
    CONSTRAINT ck_offline_archive_evidence CHECK (
        manifest_size_bytes > 0
        AND char_length(source_snapshot_sha256) = 64
        AND char_length(manifest_checksum_sha256) = 64
        AND char_length(delivery_package_checksum_sha256) = 64
    )
);

CREATE INDEX IF NOT EXISTS idx_offline_archives_task_version
    ON offline_archives (task_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_offline_archives_task_status
    ON offline_archives (task_id, status, generated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_offline_archives_current
    ON offline_archives (task_id)
    WHERE status = 'completed';

CREATE TABLE IF NOT EXISTS offline_archive_volumes (
    id SERIAL PRIMARY KEY,
    archive_id INTEGER NOT NULL
        REFERENCES offline_archives(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    filename VARCHAR(200) NOT NULL,
    file_uri VARCHAR(500) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    member_count INTEGER NOT NULL,
    source_size_bytes BIGINT NOT NULL,
    volume_manifest JSONB NOT NULL,
    CONSTRAINT uq_offline_archive_volume_sequence
        UNIQUE (archive_id, sequence),
    CONSTRAINT uq_offline_archive_volume_filename
        UNIQUE (archive_id, filename),
    CONSTRAINT ck_offline_archive_volume_evidence CHECK (
        sequence > 0
        AND member_count > 0
        AND source_size_bytes > 0
        AND file_size_bytes > 0
        AND char_length(checksum_sha256) = 64
    )
);

CREATE INDEX IF NOT EXISTS idx_offline_archive_volumes_archive_sequence
    ON offline_archive_volumes (archive_id, sequence);

CREATE TABLE IF NOT EXISTS offline_archive_sources (
    id SERIAL PRIMARY KEY,
    archive_id INTEGER NOT NULL
        REFERENCES offline_archives(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    volume_sequence INTEGER NOT NULL,
    source_kind VARCHAR(30) NOT NULL,
    source_entity_id INTEGER,
    source_entity_code VARCHAR(100) NOT NULL,
    archive_path VARCHAR(500) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_uri VARCHAR(500) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    media_type VARCHAR(120) NOT NULL,
    source_version VARCHAR(100),
    security_classification VARCHAR(30) NOT NULL,
    source_updated_at TIMESTAMPTZ,
    CONSTRAINT uq_offline_archive_source_sequence
        UNIQUE (archive_id, sequence),
    CONSTRAINT uq_offline_archive_source_path
        UNIQUE (archive_id, archive_path),
    CONSTRAINT ck_offline_archive_source_evidence CHECK (
        sequence > 0
        AND volume_sequence > 0
        AND file_size_bytes > 0
        AND char_length(checksum_sha256) = 64
    )
);

CREATE INDEX IF NOT EXISTS idx_offline_archive_sources_archive_volume
    ON offline_archive_sources (archive_id, volume_sequence, sequence);

CREATE TABLE IF NOT EXISTS offline_archive_events (
    id SERIAL PRIMARY KEY,
    archive_id INTEGER NOT NULL
        REFERENCES offline_archives(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    actor_code VARCHAR(50) NOT NULL,
    actor_role VARCHAR(40) NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_offline_archive_events_archive_time
    ON offline_archive_events (archive_id, created_at DESC);

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
    plot_code, version, owner_village, land_class, crop_type, planting_mode,
    irrigation_condition, interpretation_status, geom, change_summary,
    created_by, created_by_code, created_by_role
)
SELECT plot_code, 1, owner_village, land_class, crop_type, planting_mode,
       irrigation_condition, interpretation_status, geom, '初始基线版本',
       '系统初始化', 'system_init', 'system'
FROM farmland_plots
ON CONFLICT (plot_code, version) DO NOTHING;

INSERT INTO plot_versions (
    plot_code, version, owner_village, land_class, crop_type, planting_mode,
    irrigation_condition, interpretation_status, geom, change_summary,
    created_by, created_by_code, created_by_role
)
SELECT plot_code, version, owner_village, land_class, crop_type, planting_mode,
       irrigation_condition, interpretation_status, geom, '初始化图斑版本',
       '系统初始化', 'system_init', 'system'
FROM farmland_plots
ON CONFLICT (plot_code, version) DO NOTHING;

-- 外业记录必须通过单条采集接口或 /api/v1/field-verifications/import-csv
-- 导入真实 GPS 和现场媒体引用；初始化阶段不再生成虚构点位。
-- 2026-07-22：新增多源数据目录、生产批次、县区作业包和采购量化规则。
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
    physical_file_uri VARCHAR(500),
    physical_original_filename VARCHAR(255),
    physical_file_size_bytes BIGINT,
    physical_checksum_sha256 VARCHAR(64),
    physical_media_type VARCHAR(120),
    verified_at TIMESTAMPTZ,
    verified_by VARCHAR(100),
    verified_by_code VARCHAR(50),
    verified_by_role VARCHAR(40),
    verification_comment TEXT,
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
    CONSTRAINT ck_dataset_verified_entity CHECK (
        verification_status != 'verified'
        OR (
            physical_file_uri IS NOT NULL
            AND physical_original_filename IS NOT NULL
            AND physical_file_size_bytes > 0
            AND physical_checksum_sha256 = checksum_sha256
            AND char_length(physical_checksum_sha256) = 64
            AND physical_media_type IS NOT NULL
            AND verified_at IS NOT NULL
            AND verified_by IS NOT NULL
            AND verified_by_code IS NOT NULL
            AND verified_by_role IS NOT NULL
            AND verification_comment IS NOT NULL
        )
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

-- 多源数据资产每次补传都保留不可变核验结果；拒绝尝试不发布实体文件。
CREATE TABLE IF NOT EXISTS dataset_asset_verifications (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL
        REFERENCES dataset_assets(id) ON DELETE CASCADE,
    verification_code VARCHAR(80) NOT NULL UNIQUE,
    verification_status VARCHAR(20) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_uri VARCHAR(500),
    file_size_bytes BIGINT NOT NULL,
    expected_checksum_sha256 VARCHAR(64) NOT NULL,
    computed_checksum_sha256 VARCHAR(64) NOT NULL,
    media_type VARCHAR(120) NOT NULL,
    inspection_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    verification_error TEXT,
    operator VARCHAR(100) NOT NULL,
    operator_code VARCHAR(50) NOT NULL,
    operator_role VARCHAR(40) NOT NULL,
    verification_comment TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_dataset_asset_verification_status CHECK (
        verification_status IN ('verified', 'rejected')
    ),
    CONSTRAINT ck_dataset_asset_verification_file CHECK (
        file_size_bytes > 0
        AND char_length(expected_checksum_sha256) = 64
        AND char_length(computed_checksum_sha256) = 64
    ),
    CONSTRAINT ck_dataset_asset_verification_publication CHECK (
        (verification_status = 'verified' AND file_uri IS NOT NULL)
        OR (verification_status = 'rejected' AND file_uri IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_dataset_asset_verifications_asset_created
    ON dataset_asset_verifications (asset_id, created_at DESC);

-- 多源数据目录批量入库固定为 1–20 个文件、一次请求和一次业务事务。
CREATE TABLE IF NOT EXISTS dataset_asset_import_batches (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL
        REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    task_id INTEGER NOT NULL
        REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    batch_code VARCHAR(90) NOT NULL UNIQUE,
    item_count INTEGER NOT NULL,
    total_size_bytes BIGINT NOT NULL,
    manifest_sha256 VARCHAR(64) NOT NULL,
    imported_by VARCHAR(100) NOT NULL,
    imported_by_code VARCHAR(50) NOT NULL,
    imported_by_role VARCHAR(40) NOT NULL,
    import_comment TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_dataset_asset_import_batch_values CHECK (
        item_count BETWEEN 1 AND 20
        AND total_size_bytes > 0
        AND char_length(manifest_sha256) = 64
        AND char_length(trim(import_comment)) >= 10
    )
);

CREATE INDEX IF NOT EXISTS idx_dataset_asset_import_batches_project_created
    ON dataset_asset_import_batches (project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS dataset_asset_import_batch_items (
    id BIGSERIAL PRIMARY KEY,
    batch_id INTEGER NOT NULL
        REFERENCES dataset_asset_import_batches(id) ON DELETE CASCADE,
    asset_id INTEGER NOT NULL
        REFERENCES dataset_assets(id) ON DELETE RESTRICT,
    verification_id INTEGER NOT NULL
        REFERENCES dataset_asset_verifications(id) ON DELETE RESTRICT,
    sequence INTEGER NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_dataset_asset_import_batch_item_sequence
        UNIQUE (batch_id, sequence),
    CONSTRAINT uq_dataset_asset_import_batch_item_asset
        UNIQUE (batch_id, asset_id),
    CONSTRAINT uq_dataset_asset_import_batch_item_verification
        UNIQUE (batch_id, verification_id),
    CONSTRAINT ck_dataset_asset_import_batch_item_values CHECK (
        sequence BETWEEN 1 AND 20
        AND file_size_bytes > 0
        AND char_length(checksum_sha256) = 64
    )
);

CREATE INDEX IF NOT EXISTS idx_dataset_asset_import_batch_items_batch
    ON dataset_asset_import_batch_items (batch_id, sequence);

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

-- 2026-07-22：新增多时相变化检测任务、候选 GeoJSON 和人工判读审计。
-- 任务必须绑定两期真实影像、规则版本、任务范围快照与配准证据。
CREATE TABLE IF NOT EXISTS change_detection_runs (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL
        REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    task_id INTEGER NOT NULL
        REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    run_code VARCHAR(80) NOT NULL UNIQUE,
    run_name VARCHAR(200) NOT NULL,
    baseline_asset_id INTEGER NOT NULL
        REFERENCES imagery_assets(id) ON DELETE RESTRICT,
    target_asset_id INTEGER NOT NULL
        REFERENCES imagery_assets(id) ON DELETE RESTRICT,
    registration_job_id INTEGER
        REFERENCES imagery_registration_jobs(id) ON DELETE RESTRICT,
    rule_config_version INTEGER NOT NULL,
    rule_profile_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    task_plot_count INTEGER NOT NULL,
    task_updated_at_snapshot TIMESTAMPTZ NOT NULL,
    alignment_method VARCHAR(120) NOT NULL,
    alignment_offset_pixels NUMERIC(8, 3) NOT NULL,
    alignment_overlap_ratio NUMERIC(7, 4) NOT NULL,
    alignment_evidence_uri VARCHAR(500) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    created_by VARCHAR(100) NOT NULL,
    created_by_code VARCHAR(50) NOT NULL,
    created_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_change_run_assets CHECK (
        baseline_asset_id != target_asset_id
    ),
    CONSTRAINT ck_change_run_plot_count CHECK (task_plot_count > 0),
    CONSTRAINT ck_change_run_alignment CHECK (
        alignment_offset_pixels >= 0
        AND alignment_overlap_ratio > 0
        AND alignment_overlap_ratio <= 1
    ),
    CONSTRAINT ck_change_run_status CHECK (
        status IN ('active', 'reviewing', 'completed', 'cancelled')
    )
);

CREATE INDEX IF NOT EXISTS idx_change_detection_runs_task_status
    ON change_detection_runs (task_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS change_candidates (
    id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL
        REFERENCES change_detection_runs(id) ON DELETE CASCADE,
    candidate_code VARCHAR(80) NOT NULL,
    source_name VARCHAR(120) NOT NULL,
    source_uri VARCHAR(500) NOT NULL,
    source_version VARCHAR(80) NOT NULL,
    source_feature_id VARCHAR(100) NOT NULL,
    source_checksum_sha256 VARCHAR(64) NOT NULL,
    import_batch_code VARCHAR(100) NOT NULL,
    change_class VARCHAR(60) NOT NULL,
    confidence NUMERIC(6, 5) NOT NULL,
    area_ha NUMERIC(16, 4) NOT NULL,
    evidence_uri VARCHAR(500) NOT NULL,
    geom GEOMETRY(POLYGON, 4326) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    exclusion_reason TEXT,
    review_comment TEXT,
    reviewed_by VARCHAR(100),
    reviewed_by_code VARCHAR(50),
    reviewed_by_role VARCHAR(40),
    reviewed_at TIMESTAMPTZ,
    imported_by VARCHAR(100) NOT NULL,
    imported_by_code VARCHAR(50) NOT NULL,
    imported_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_change_candidate_code UNIQUE (run_id, candidate_code),
    CONSTRAINT uq_change_candidate_source UNIQUE (
        run_id, source_name, source_feature_id
    ),
    CONSTRAINT ck_change_candidate_class CHECK (
        change_class IN (
            'unclassified',
            'suspected_construction',
            'farmland_outflow',
            'construction_facility_change',
            'non_farmland_agricultural_change',
            'unused_land_change',
            'farmland_attribute_change'
        )
    ),
    CONSTRAINT ck_change_candidate_confidence CHECK (
        confidence >= 0 AND confidence <= 1
    ),
    CONSTRAINT ck_change_candidate_area CHECK (area_ha > 0),
    CONSTRAINT ck_change_candidate_status CHECK (
        status IN ('pending', 'confirmed', 'excluded')
    ),
    CONSTRAINT ck_change_candidate_exclusion CHECK (
        status != 'excluded' OR exclusion_reason IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_change_candidates_run_status
    ON change_candidates (run_id, status, change_class);
CREATE INDEX IF NOT EXISTS idx_change_candidates_import_batch
    ON change_candidates (run_id, import_batch_code);
CREATE INDEX IF NOT EXISTS idx_change_candidates_geom
    ON change_candidates USING GIST (geom);

CREATE TABLE IF NOT EXISTS change_detection_events (
    id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL
        REFERENCES change_detection_runs(id) ON DELETE CASCADE,
    candidate_id INTEGER
        REFERENCES change_candidates(id) ON DELETE CASCADE,
    event_type VARCHAR(40) NOT NULL,
    previous_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    new_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    comment TEXT NOT NULL,
    operator VARCHAR(100) NOT NULL,
    operator_code VARCHAR(50) NOT NULL,
    operator_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_change_detection_events_run_time
    ON change_detection_events (run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_change_detection_events_candidate_time
    ON change_detection_events (candidate_id, created_at DESC)
    WHERE candidate_id IS NOT NULL;

-- 独立项目监理首个可交付闭环。
-- 与自动质检、内业自检、质检审核和甲方复核分离，保存真实抽样与不可变证据。

CREATE TABLE IF NOT EXISTS supervision_plans (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL
        REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    task_id INTEGER NOT NULL
        REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    plan_code VARCHAR(80) NOT NULL UNIQUE,
    plan_name VARCHAR(200) NOT NULL,
    sampling_method VARCHAR(30) NOT NULL,
    sample_ratio NUMERIC(7, 4) NOT NULL,
    minimum_per_region INTEGER NOT NULL,
    region_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    task_plot_count_snapshot INTEGER NOT NULL,
    task_updated_at_snapshot TIMESTAMPTZ NOT NULL,
    planned_start_date DATE NOT NULL,
    planned_end_date DATE NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    created_by VARCHAR(100) NOT NULL,
    created_by_code VARCHAR(50) NOT NULL,
    created_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_supervision_plan_sampling_method CHECK (
        sampling_method IN ('systematic', 'stratified_random')
    ),
    CONSTRAINT ck_supervision_plan_ratio CHECK (
        sample_ratio >= 0.1 AND sample_ratio <= 100
    ),
    CONSTRAINT ck_supervision_plan_minimum CHECK (
        minimum_per_region >= 1 AND minimum_per_region <= 500
    ),
    CONSTRAINT ck_supervision_plan_task_count CHECK (
        task_plot_count_snapshot > 0
    ),
    CONSTRAINT ck_supervision_plan_dates CHECK (
        planned_end_date >= planned_start_date
    ),
    CONSTRAINT ck_supervision_plan_status CHECK (
        status IN ('active', 'completed', 'cancelled')
    )
);

CREATE INDEX IF NOT EXISTS idx_supervision_plans_task_status
    ON supervision_plans (task_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS supervision_samples (
    id SERIAL PRIMARY KEY,
    plan_id INTEGER NOT NULL
        REFERENCES supervision_plans(id) ON DELETE CASCADE,
    plot_code VARCHAR(50) NOT NULL
        REFERENCES farmland_plots(plot_code) ON DELETE RESTRICT,
    region_code VARCHAR(50) NOT NULL,
    region_name VARCHAR(100) NOT NULL,
    plot_version_snapshot INTEGER NOT NULL,
    selection_rank INTEGER NOT NULL,
    selected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_supervision_sample_plot UNIQUE (plan_id, plot_code),
    CONSTRAINT ck_supervision_sample_version CHECK (plot_version_snapshot > 0),
    CONSTRAINT ck_supervision_sample_rank CHECK (selection_rank > 0)
);

CREATE INDEX IF NOT EXISTS idx_supervision_samples_plan_region
    ON supervision_samples (plan_id, region_code, selection_rank);
CREATE INDEX IF NOT EXISTS idx_supervision_samples_plot
    ON supervision_samples (plot_code);

CREATE TABLE IF NOT EXISTS supervision_inspections (
    id SERIAL PRIMARY KEY,
    plan_id INTEGER NOT NULL
        REFERENCES supervision_plans(id) ON DELETE CASCADE,
    inspection_code VARCHAR(80) NOT NULL,
    inspection_stage VARCHAR(40) NOT NULL,
    inspected_at TIMESTAMPTZ NOT NULL,
    conclusion VARCHAR(30) NOT NULL,
    evidence_uri VARCHAR(500) NOT NULL,
    summary TEXT NOT NULL,
    inspector VARCHAR(100) NOT NULL,
    inspector_code VARCHAR(50) NOT NULL,
    inspector_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_supervision_inspection_code UNIQUE (
        plan_id, inspection_code
    ),
    CONSTRAINT ck_supervision_inspection_stage CHECK (
        inspection_stage IN (
            'imagery_processing',
            'plot_interpretation',
            'quality_control',
            'field_verification',
            'review_delivery'
        )
    ),
    CONSTRAINT ck_supervision_inspection_conclusion CHECK (
        conclusion IN ('passed', 'conditional', 'failed')
    )
);

CREATE INDEX IF NOT EXISTS idx_supervision_inspections_plan_time
    ON supervision_inspections (plan_id, inspected_at DESC);

CREATE TABLE IF NOT EXISTS supervision_findings (
    id SERIAL PRIMARY KEY,
    inspection_id INTEGER NOT NULL
        REFERENCES supervision_inspections(id) ON DELETE CASCADE,
    sample_id INTEGER
        REFERENCES supervision_samples(id) ON DELETE SET NULL,
    finding_code VARCHAR(80) NOT NULL,
    region_code VARCHAR(50) NOT NULL,
    region_name VARCHAR(100) NOT NULL,
    issue_type VARCHAR(60) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    description TEXT NOT NULL,
    evidence_uri VARCHAR(500) NOT NULL,
    rework_deadline DATE NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'open',
    rectification_comment TEXT,
    rectification_evidence_uri VARCHAR(500),
    rectified_by VARCHAR(100),
    rectified_by_code VARCHAR(50),
    rectified_by_role VARCHAR(40),
    rectified_at TIMESTAMPTZ,
    created_by VARCHAR(100) NOT NULL,
    created_by_code VARCHAR(50) NOT NULL,
    created_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_supervision_finding_code UNIQUE (
        inspection_id, finding_code
    ),
    CONSTRAINT ck_supervision_finding_severity CHECK (
        severity IN ('minor', 'major', 'critical')
    ),
    CONSTRAINT ck_supervision_finding_status CHECK (
        status IN (
            'open',
            'rectification_submitted',
            'rework_required',
            'closed'
        )
    ),
    CONSTRAINT ck_supervision_finding_rectification CHECK (
        status = 'open'
        OR (
            rectification_comment IS NOT NULL
            AND rectification_evidence_uri IS NOT NULL
            AND rectified_by_code IS NOT NULL
            AND rectified_at IS NOT NULL
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_supervision_findings_status_deadline
    ON supervision_findings (status, rework_deadline);
CREATE INDEX IF NOT EXISTS idx_supervision_findings_region
    ON supervision_findings (region_code, severity, status);

CREATE TABLE IF NOT EXISTS supervision_reinspections (
    id SERIAL PRIMARY KEY,
    finding_id INTEGER NOT NULL
        REFERENCES supervision_findings(id) ON DELETE CASCADE,
    round_no INTEGER NOT NULL,
    result VARCHAR(20) NOT NULL,
    comment TEXT NOT NULL,
    evidence_uri VARCHAR(500) NOT NULL,
    inspector VARCHAR(100) NOT NULL,
    inspector_code VARCHAR(50) NOT NULL,
    inspector_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_supervision_reinspection_round UNIQUE (
        finding_id, round_no
    ),
    CONSTRAINT ck_supervision_reinspection_round CHECK (round_no > 0),
    CONSTRAINT ck_supervision_reinspection_result CHECK (
        result IN ('passed', 'failed')
    )
);

CREATE INDEX IF NOT EXISTS idx_supervision_reinspections_finding_time
    ON supervision_reinspections (finding_id, round_no);

CREATE TABLE IF NOT EXISTS supervision_county_evaluations (
    id SERIAL PRIMARY KEY,
    plan_id INTEGER NOT NULL
        REFERENCES supervision_plans(id) ON DELETE CASCADE,
    region_code VARCHAR(50) NOT NULL,
    region_name VARCHAR(100) NOT NULL,
    quality_score NUMERIC(5, 2) NOT NULL,
    timeliness_score NUMERIC(5, 2) NOT NULL,
    compliance_score NUMERIC(5, 2) NOT NULL,
    overall_score NUMERIC(5, 2) NOT NULL,
    grade VARCHAR(20) NOT NULL,
    comment TEXT NOT NULL,
    evaluated_by VARCHAR(100) NOT NULL,
    evaluated_by_code VARCHAR(50) NOT NULL,
    evaluated_by_role VARCHAR(40) NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_supervision_county_evaluation UNIQUE (
        plan_id, region_code
    ),
    CONSTRAINT ck_supervision_county_scores CHECK (
        quality_score >= 0 AND quality_score <= 100
        AND timeliness_score >= 0 AND timeliness_score <= 100
        AND compliance_score >= 0 AND compliance_score <= 100
        AND overall_score >= 0 AND overall_score <= 100
    ),
    CONSTRAINT ck_supervision_county_grade CHECK (
        grade IN ('A', 'B', 'C', 'D')
    )
);

CREATE INDEX IF NOT EXISTS idx_supervision_county_plan_grade
    ON supervision_county_evaluations (plan_id, grade, overall_score);

CREATE TABLE IF NOT EXISTS supervision_reports (
    id SERIAL PRIMARY KEY,
    plan_id INTEGER NOT NULL UNIQUE
        REFERENCES supervision_plans(id) ON DELETE RESTRICT,
    report_code VARCHAR(100) NOT NULL UNIQUE,
    file_uri VARCHAR(500) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    evidence_manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
    generated_by VARCHAR(100) NOT NULL,
    generated_by_code VARCHAR(50) NOT NULL,
    generated_by_role VARCHAR(40) NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_supervision_report_size CHECK (file_size_bytes > 0),
    CONSTRAINT ck_supervision_report_checksum CHECK (
        char_length(checksum_sha256) = 64
    )
);

CREATE TABLE IF NOT EXISTS supervision_events (
    id SERIAL PRIMARY KEY,
    plan_id INTEGER NOT NULL
        REFERENCES supervision_plans(id) ON DELETE CASCADE,
    entity_type VARCHAR(40) NOT NULL,
    entity_code VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    previous_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    new_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    comment TEXT NOT NULL,
    operator VARCHAR(100) NOT NULL,
    operator_code VARCHAR(50) NOT NULL,
    operator_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_supervision_events_plan_time
    ON supervision_events (plan_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_supervision_events_entity
    ON supervision_events (entity_type, entity_code, created_at DESC);


-- 专题制图模板、实体成果和不可变审计。
CREATE TABLE IF NOT EXISTS thematic_map_templates (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL
        REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    template_code VARCHAR(80) NOT NULL,
    template_name VARCHAR(150) NOT NULL,
    title_pattern VARCHAR(200) NOT NULL,
    producer VARCHAR(150) NOT NULL,
    page_width_px INTEGER NOT NULL,
    page_height_px INTEGER NOT NULL,
    dpi INTEGER NOT NULL,
    margin_px INTEGER NOT NULL,
    legend_position VARCHAR(30) NOT NULL,
    include_neatline BOOLEAN NOT NULL DEFAULT TRUE,
    include_north_arrow BOOLEAN NOT NULL DEFAULT TRUE,
    include_scale_bar BOOLEAN NOT NULL DEFAULT TRUE,
    created_by VARCHAR(100) NOT NULL,
    created_by_code VARCHAR(50) NOT NULL,
    created_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_thematic_map_template_project_code
        UNIQUE (project_id, template_code),
    CONSTRAINT ck_thematic_map_template_dimensions CHECK (
        page_width_px BETWEEN 800 AND 8000
        AND page_height_px BETWEEN 600 AND 8000
    ),
    CONSTRAINT ck_thematic_map_template_print CHECK (
        dpi BETWEEN 72 AND 600
        AND margin_px BETWEEN 20 AND 800
    ),
    CONSTRAINT ck_thematic_map_template_legend_position CHECK (
        legend_position IN ('bottom_right', 'bottom_left')
    )
);

CREATE INDEX IF NOT EXISTS idx_thematic_map_templates_project_time
    ON thematic_map_templates (project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS thematic_map_products (
    id SERIAL PRIMARY KEY,
    template_id INTEGER NOT NULL
        REFERENCES thematic_map_templates(id) ON DELETE RESTRICT,
    task_id INTEGER NOT NULL
        REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    asset_id INTEGER NOT NULL
        REFERENCES imagery_assets(id) ON DELETE RESTRICT,
    product_code VARCHAR(100) NOT NULL,
    map_name VARCHAR(200) NOT NULL,
    map_number VARCHAR(100) NOT NULL,
    map_date DATE NOT NULL,
    source_product_code VARCHAR(30) NOT NULL,
    output_format VARCHAR(10) NOT NULL,
    status VARCHAR(20) NOT NULL,
    file_uri VARCHAR(500) NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    page_width_px INTEGER NOT NULL,
    page_height_px INTEGER NOT NULL,
    dpi INTEGER NOT NULL,
    source_uri VARCHAR(500) NOT NULL,
    source_checksum_sha256 VARCHAR(64) NOT NULL,
    source_bounds_wgs84 JSONB NOT NULL,
    render_manifest JSONB NOT NULL,
    generated_by VARCHAR(100) NOT NULL,
    generated_by_code VARCHAR(50) NOT NULL,
    generated_by_role VARCHAR(40) NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_thematic_map_product_code UNIQUE (product_code),
    CONSTRAINT uq_thematic_map_product_business_key UNIQUE (
        task_id, map_number, source_product_code, output_format
    ),
    CONSTRAINT ck_thematic_map_product_source_code CHECK (
        source_product_code IN ('true_color', 'false_color', 'ndvi')
    ),
    CONSTRAINT ck_thematic_map_product_format CHECK (
        output_format IN ('png', 'pdf')
    ),
    CONSTRAINT ck_thematic_map_product_status CHECK (
        status IN ('completed', 'invalid')
    ),
    CONSTRAINT ck_thematic_map_product_file_evidence CHECK (
        file_size_bytes > 0
        AND char_length(checksum_sha256) = 64
    )
);

CREATE INDEX IF NOT EXISTS idx_thematic_map_products_task_time
    ON thematic_map_products (task_id, generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_thematic_map_products_asset_source
    ON thematic_map_products (asset_id, source_product_code, output_format);

CREATE TABLE IF NOT EXISTS thematic_map_atlases (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL
        REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    atlas_code VARCHAR(100) NOT NULL,
    atlas_name VARCHAR(200) NOT NULL,
    atlas_number VARCHAR(100) NOT NULL,
    version INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    package_uri VARCHAR(500) NOT NULL,
    package_size_bytes INTEGER NOT NULL,
    package_checksum_sha256 VARCHAR(64) NOT NULL,
    pdf_filename VARCHAR(200) NOT NULL,
    pdf_size_bytes INTEGER NOT NULL,
    pdf_checksum_sha256 VARCHAR(64) NOT NULL,
    pdf_page_count INTEGER NOT NULL,
    member_count INTEGER NOT NULL,
    product_count_snapshot INTEGER NOT NULL,
    product_latest_at_snapshot TIMESTAMPTZ NOT NULL,
    source_snapshot_sha256 VARCHAR(64) NOT NULL,
    atlas_manifest JSONB NOT NULL,
    generated_by VARCHAR(100) NOT NULL,
    generated_by_code VARCHAR(50) NOT NULL,
    generated_by_role VARCHAR(40) NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    superseded_at TIMESTAMPTZ,
    CONSTRAINT uq_thematic_map_atlas_code UNIQUE (atlas_code),
    CONSTRAINT uq_thematic_map_atlas_task_version UNIQUE (task_id, version),
    CONSTRAINT ck_thematic_map_atlas_status CHECK (
        status IN ('completed', 'superseded', 'invalid')
    ),
    CONSTRAINT ck_thematic_map_atlas_counts CHECK (
        member_count BETWEEN 2 AND 50
        AND pdf_page_count >= member_count + 2
    ),
    CONSTRAINT ck_thematic_map_atlas_file_evidence CHECK (
        package_size_bytes > 0
        AND pdf_size_bytes > 0
        AND char_length(package_checksum_sha256) = 64
        AND char_length(pdf_checksum_sha256) = 64
        AND char_length(source_snapshot_sha256) = 64
    )
);

CREATE INDEX IF NOT EXISTS idx_thematic_map_atlases_task_version
    ON thematic_map_atlases (task_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_thematic_map_atlases_task_status
    ON thematic_map_atlases (task_id, status, generated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_thematic_map_atlases_current
    ON thematic_map_atlases (task_id)
    WHERE status = 'completed';

CREATE TABLE IF NOT EXISTS thematic_map_atlas_items (
    id SERIAL PRIMARY KEY,
    atlas_id INTEGER NOT NULL
        REFERENCES thematic_map_atlases(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL
        REFERENCES thematic_map_products(id) ON DELETE RESTRICT,
    sequence INTEGER NOT NULL,
    product_code VARCHAR(100) NOT NULL,
    map_name VARCHAR(200) NOT NULL,
    map_number VARCHAR(100) NOT NULL,
    map_date DATE NOT NULL,
    product_size_bytes INTEGER NOT NULL,
    product_checksum_sha256 VARCHAR(64) NOT NULL,
    member_path VARCHAR(300) NOT NULL,
    CONSTRAINT uq_thematic_map_atlas_item_sequence
        UNIQUE (atlas_id, sequence),
    CONSTRAINT uq_thematic_map_atlas_item_product
        UNIQUE (atlas_id, product_id),
    CONSTRAINT ck_thematic_map_atlas_item_evidence CHECK (
        sequence BETWEEN 1 AND 50
        AND product_size_bytes > 0
        AND char_length(product_checksum_sha256) = 64
    )
);

CREATE INDEX IF NOT EXISTS idx_thematic_map_atlas_items_atlas_sequence
    ON thematic_map_atlas_items (atlas_id, sequence);

CREATE TABLE IF NOT EXISTS thematic_map_events (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL
        REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    entity_type VARCHAR(40) NOT NULL,
    entity_code VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    event_values JSONB NOT NULL,
    comment TEXT NOT NULL,
    operator VARCHAR(100) NOT NULL,
    operator_code VARCHAR(50) NOT NULL,
    operator_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_thematic_map_events_task_time
    ON thematic_map_events (task_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_thematic_map_events_entity
    ON thematic_map_events (entity_type, entity_code, created_at DESC);

-- 受控地图/数据服务注册、审批、凭证、健康、调用审计和撤销闭环。
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

-- 病虫害监测报告、显式识别台账、三级审核与专家会商闭环。

CREATE TABLE IF NOT EXISTS pest_reports (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    report_code VARCHAR(80) NOT NULL,
    report_title VARCHAR(240) NOT NULL,
    scope_level VARCHAR(20) NOT NULL,
    region_code VARCHAR(50) NOT NULL,
    region_name VARCHAR(100) NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    summary TEXT NOT NULL,
    conclusion TEXT NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'draft',
    revision_number INTEGER NOT NULL DEFAULT 1 CHECK (revision_number > 0),
    assessment_count INTEGER NOT NULL DEFAULT 0 CHECK (assessment_count >= 0),
    alert_count INTEGER NOT NULL DEFAULT 0 CHECK (alert_count >= 0),
    snapshot_at TIMESTAMPTZ NOT NULL,
    file_uri VARCHAR(500),
    original_filename VARCHAR(255),
    file_size_bytes BIGINT CHECK (file_size_bytes > 0),
    checksum_sha256 VARCHAR(64),
    created_by VARCHAR(100) NOT NULL,
    created_by_code VARCHAR(50) NOT NULL,
    created_by_role VARCHAR(40) NOT NULL,
    last_review_comment TEXT,
    approved_by VARCHAR(100),
    approved_by_code VARCHAR(50),
    approved_by_role VARCHAR(40),
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_pest_report_code UNIQUE (project_id, report_code),
    CONSTRAINT ck_pest_report_period CHECK (period_end >= period_start),
    CONSTRAINT ck_pest_report_scope CHECK (
        scope_level IN ('province', 'prefecture', 'county')
    ),
    CONSTRAINT ck_pest_report_status CHECK (
        status IN (
            'draft', 'county_review', 'prefecture_review',
            'province_review', 'returned', 'approved'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_pest_reports_project_status
    ON pest_reports (project_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_pest_reports_region_period
    ON pest_reports (scope_level, region_code, period_start, period_end);

CREATE TABLE IF NOT EXISTS pest_report_items (
    id BIGSERIAL PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES pest_reports(id) ON DELETE CASCADE,
    assessment_id INTEGER NOT NULL REFERENCES pest_assessments(id) ON DELETE RESTRICT,
    assessment_code VARCHAR(80) NOT NULL,
    district_code VARCHAR(50) NOT NULL,
    district_name VARCHAR(100) NOT NULL,
    snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_pest_report_assessment UNIQUE (report_id, assessment_id)
);

CREATE INDEX IF NOT EXISTS idx_pest_report_items_report
    ON pest_report_items (report_id, assessment_code);
CREATE INDEX IF NOT EXISTS idx_pest_report_items_district
    ON pest_report_items (district_code, assessment_code);

CREATE TABLE IF NOT EXISTS expert_consultations (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    report_id INTEGER NOT NULL REFERENCES pest_reports(id) ON DELETE CASCADE,
    consultation_code VARCHAR(80) NOT NULL,
    question TEXT NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'open',
    requested_by VARCHAR(100) NOT NULL,
    requested_by_code VARCHAR(50) NOT NULL,
    requested_by_role VARCHAR(40) NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expert_organization VARCHAR(200),
    expert_title VARCHAR(120),
    response TEXT,
    evidence_uri VARCHAR(500),
    evidence_filename VARCHAR(255),
    evidence_size_bytes BIGINT CHECK (evidence_size_bytes > 0),
    evidence_sha256 VARCHAR(64),
    answered_by VARCHAR(100),
    answered_by_code VARCHAR(50),
    answered_by_role VARCHAR(40),
    answered_at TIMESTAMPTZ,
    CONSTRAINT uq_expert_consultation_code UNIQUE (project_id, consultation_code),
    CONSTRAINT ck_expert_consultation_status CHECK (status IN ('open', 'answered'))
);

CREATE INDEX IF NOT EXISTS idx_expert_consultations_report_status
    ON expert_consultations (report_id, status, requested_at DESC);

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
