-- 2026-07-23：外业照片、语音和调查表从外链升级为受控实体证据。
-- 保存服务端计算的大小与 SHA-256，并记录稳定项目用户的上传/下载事件。

BEGIN;

ALTER TABLE field_verifications
    ADD COLUMN IF NOT EXISTS source_file_uri VARCHAR(500);
ALTER TABLE field_verifications
    ADD COLUMN IF NOT EXISTS source_file_size_bytes BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_field_verification_source_file_size'
    ) THEN
        ALTER TABLE field_verifications
            ADD CONSTRAINT ck_field_verification_source_file_size
            CHECK (
                source_file_size_bytes IS NULL
                OR source_file_size_bytes > 0
            );
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS field_verification_artifacts (
    id SERIAL PRIMARY KEY,
    field_verification_id INTEGER NOT NULL
        REFERENCES field_verifications(id) ON DELETE CASCADE,
    artifact_code VARCHAR(80) NOT NULL UNIQUE,
    artifact_type VARCHAR(20) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    media_type VARCHAR(100) NOT NULL,
    file_uri VARCHAR(500) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    description TEXT NOT NULL,
    uploaded_by VARCHAR(100) NOT NULL,
    uploaded_by_code VARCHAR(50) NOT NULL,
    uploaded_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_field_verification_artifact_checksum
        UNIQUE (field_verification_id, checksum_sha256),
    CONSTRAINT ck_field_verification_artifact_type
        CHECK (artifact_type IN ('photo', 'voice', 'form')),
    CONSTRAINT ck_field_verification_artifact_size
        CHECK (file_size_bytes > 0),
    CONSTRAINT ck_field_verification_artifact_checksum
        CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS idx_field_verification_artifacts_record_type
    ON field_verification_artifacts (field_verification_id, artifact_type);

CREATE TABLE IF NOT EXISTS field_verification_artifact_events (
    id SERIAL PRIMARY KEY,
    field_verification_id INTEGER NOT NULL
        REFERENCES field_verifications(id) ON DELETE CASCADE,
    artifact_id INTEGER
        REFERENCES field_verification_artifacts(id) ON DELETE SET NULL,
    event_type VARCHAR(20) NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    actor VARCHAR(100) NOT NULL,
    actor_code VARCHAR(50) NOT NULL,
    actor_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_field_verification_artifact_event_type
        CHECK (event_type IN ('uploaded', 'downloaded'))
);

CREATE INDEX IF NOT EXISTS idx_field_verification_artifact_events_record_time
    ON field_verification_artifact_events (
        field_verification_id,
        created_at DESC
    );

COMMIT;
