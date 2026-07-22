BEGIN;

-- 历史年度统计必须保存实体来源、文件校验和稳定项目用户审计。
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

COMMIT;
