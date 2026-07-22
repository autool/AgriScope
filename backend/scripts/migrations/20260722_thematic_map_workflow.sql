-- 新增专题制图模板、实体成果和不可变审计。


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
