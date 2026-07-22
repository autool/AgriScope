-- 新增任务作用域多格式矢量成果包，真实生成 GeoJSON、Shapefile、
-- KML 和 OpenFileGDB，并保存筛选、版本、实体及稳定用户审计。

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
