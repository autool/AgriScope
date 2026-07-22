-- 新增项目级质量和外业空间校核规则配置，并保存每次修改的前后值审计。

BEGIN;

CREATE TABLE IF NOT EXISTS project_rule_configs (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL UNIQUE
        REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    field_offset_threshold_m NUMERIC(8, 2) NOT NULL DEFAULT 5.00,
    field_search_radius_m NUMERIC(10, 2) NOT NULL DEFAULT 1000.00,
    positional_accuracy_pixels NUMERIC(6, 2) NOT NULL DEFAULT 2.00,
    max_capture_image_days INTEGER NOT NULL DEFAULT 15,
    updated_by VARCHAR(100) NOT NULL DEFAULT '系统默认配置',
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
    previous_values JSONB NOT NULL,
    new_values JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rule_config_audits_project_time
    ON project_rule_config_audits (project_id, created_at DESC);

INSERT INTO project_rule_configs (
    project_id, field_offset_threshold_m, field_search_radius_m,
    positional_accuracy_pixels, max_capture_image_days, updated_by
)
SELECT id, 5.00, 1000.00, 2.00, 15, '系统默认配置'
FROM monitoring_projects
WHERE project_code = 'RS-2026'
ON CONFLICT (project_id) DO NOTHING;

COMMIT;
