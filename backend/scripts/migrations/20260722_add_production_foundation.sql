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
