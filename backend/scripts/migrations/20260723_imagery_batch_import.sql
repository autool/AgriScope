-- 真实影像批量入库：保存原子批次摘要、逐文件实体证据和稳定用户审计。

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
