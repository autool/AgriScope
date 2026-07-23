-- 项目级地块自定义属性：定义审计、图斑/版本 JSONB 与 Excel 模式快照。

ALTER TABLE farmland_plots
    ADD COLUMN IF NOT EXISTS custom_attributes JSONB NOT NULL
    DEFAULT '{}'::jsonb;

ALTER TABLE plot_versions
    ADD COLUMN IF NOT EXISTS custom_attributes JSONB NOT NULL
    DEFAULT '{}'::jsonb;

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
        CHECK (
            field_type IN (
                'text', 'number', 'date', 'boolean', 'single_select'
            )
        ),
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
    ON project_plot_attribute_fields (
        project_id,
        status,
        display_order,
        id
    );

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
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_plot_attribute_import_definition_digest'
    ) THEN
        ALTER TABLE plot_attribute_import_batches
            ADD CONSTRAINT ck_plot_attribute_import_definition_digest
            CHECK (char_length(definition_digest) = 64);
    END IF;
END
$$;
