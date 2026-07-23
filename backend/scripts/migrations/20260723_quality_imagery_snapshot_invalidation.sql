-- 为不可变全量质检批次补充实际质量判定影像的规范化快照与 SHA-256。
-- 历史批次无法可靠还原当时的最新影像，显式标记为 legacy_unavailable，
-- 使其不能继续作为新版本提交门禁证据。

ALTER TABLE task_quality_runs
    ADD COLUMN IF NOT EXISTS imagery_snapshot JSONB NOT NULL
    DEFAULT '{"state":"legacy_unavailable"}'::jsonb;

ALTER TABLE task_quality_runs
    ADD COLUMN IF NOT EXISTS imagery_snapshot_digest VARCHAR(64);

UPDATE task_quality_runs
SET imagery_snapshot = '{"state":"legacy_unavailable"}'::jsonb,
    imagery_snapshot_digest = (
        '149142d0322d391de7bc805da4aa9fa41e49951e8f24c8bb207fc6ab99b6a5f7'
    )
WHERE imagery_snapshot_digest IS NULL;

ALTER TABLE task_quality_runs
    ALTER COLUMN imagery_snapshot_digest SET NOT NULL;

DO $$
BEGIN
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
