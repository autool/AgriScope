-- 新增多源数据资产 1–20 文件原子批量入库批次和逐文件成员证据。

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
    manifest_payload JSONB NOT NULL,
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
