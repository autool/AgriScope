-- 地块属性 Excel 逐行导入导出：补齐权属村版本快照并保存原始工作簿证据。

ALTER TABLE plot_versions
    ADD COLUMN IF NOT EXISTS owner_village VARCHAR(100);

-- 历史版本此前没有该字段，只能以当前图斑权属村补齐遗留快照；
-- 新版本从本迁移起保存操作时的真实权属村值。
UPDATE plot_versions AS version_row
SET owner_village = plot.owner_village
FROM farmland_plots AS plot
WHERE plot.plot_code = version_row.plot_code
  AND version_row.owner_village IS NULL;

CREATE TABLE IF NOT EXISTS plot_attribute_import_batches (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL
        REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    batch_code VARCHAR(90) NOT NULL UNIQUE,
    original_filename VARCHAR(255) NOT NULL,
    file_uri VARCHAR(500) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
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
        CHECK (char_length(checksum_sha256) = 64)
);

CREATE INDEX IF NOT EXISTS idx_plot_attribute_import_batches_task_time
    ON plot_attribute_import_batches (task_id, imported_at DESC);
