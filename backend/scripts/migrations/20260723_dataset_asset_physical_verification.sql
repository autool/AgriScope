-- 为多源数据目录补充受控实体、不可变核验尝试和下载前复核所需字段。

ALTER TABLE dataset_assets
    ADD COLUMN IF NOT EXISTS physical_file_uri VARCHAR(500),
    ADD COLUMN IF NOT EXISTS physical_original_filename VARCHAR(255),
    ADD COLUMN IF NOT EXISTS physical_file_size_bytes BIGINT,
    ADD COLUMN IF NOT EXISTS physical_checksum_sha256 VARCHAR(64),
    ADD COLUMN IF NOT EXISTS physical_media_type VARCHAR(120),
    ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS verified_by VARCHAR(100),
    ADD COLUMN IF NOT EXISTS verified_by_code VARCHAR(50),
    ADD COLUMN IF NOT EXISTS verified_by_role VARCHAR(40),
    ADD COLUMN IF NOT EXISTS verification_comment TEXT;

-- 历史版本可能只凭调用方校验值标记 verified；缺少物理证据时恢复为待核验。
UPDATE dataset_assets
SET verification_status = 'pending',
    updated_at = NOW()
WHERE verification_status = 'verified'
  AND (
      physical_file_uri IS NULL
      OR physical_original_filename IS NULL
      OR physical_file_size_bytes IS NULL
      OR physical_checksum_sha256 IS NULL
      OR physical_media_type IS NULL
      OR verified_at IS NULL
      OR verified_by IS NULL
      OR verified_by_code IS NULL
      OR verified_by_role IS NULL
      OR verification_comment IS NULL
  );

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_dataset_verified_entity'
    ) THEN
        ALTER TABLE dataset_assets
            ADD CONSTRAINT ck_dataset_verified_entity CHECK (
                verification_status != 'verified'
                OR (
                    physical_file_uri IS NOT NULL
                    AND physical_original_filename IS NOT NULL
                    AND physical_file_size_bytes > 0
                    AND physical_checksum_sha256 = checksum_sha256
                    AND char_length(physical_checksum_sha256) = 64
                    AND physical_media_type IS NOT NULL
                    AND verified_at IS NOT NULL
                    AND verified_by IS NOT NULL
                    AND verified_by_code IS NOT NULL
                    AND verified_by_role IS NOT NULL
                    AND verification_comment IS NOT NULL
                )
            );
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS dataset_asset_verifications (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL
        REFERENCES dataset_assets(id) ON DELETE CASCADE,
    verification_code VARCHAR(80) NOT NULL UNIQUE,
    verification_status VARCHAR(20) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_uri VARCHAR(500),
    file_size_bytes BIGINT NOT NULL,
    expected_checksum_sha256 VARCHAR(64) NOT NULL,
    computed_checksum_sha256 VARCHAR(64) NOT NULL,
    media_type VARCHAR(120) NOT NULL,
    inspection_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    verification_error TEXT,
    operator VARCHAR(100) NOT NULL,
    operator_code VARCHAR(50) NOT NULL,
    operator_role VARCHAR(40) NOT NULL,
    verification_comment TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_dataset_asset_verification_status CHECK (
        verification_status IN ('verified', 'rejected')
    ),
    CONSTRAINT ck_dataset_asset_verification_file CHECK (
        file_size_bytes > 0
        AND char_length(expected_checksum_sha256) = 64
        AND char_length(computed_checksum_sha256) = 64
    ),
    CONSTRAINT ck_dataset_asset_verification_publication CHECK (
        (verification_status = 'verified' AND file_uri IS NOT NULL)
        OR (verification_status = 'rejected' AND file_uri IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_dataset_asset_verifications_asset_created
    ON dataset_asset_verifications (asset_id, created_at DESC);
