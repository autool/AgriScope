BEGIN;

-- 外业记录补充来源、批次校验和稳定上传人审计，支持真实 CSV 批量导入。
ALTER TABLE field_verifications
    ADD COLUMN IF NOT EXISTS source_name VARCHAR(120);
ALTER TABLE field_verifications
    ADD COLUMN IF NOT EXISTS source_uri VARCHAR(500);
ALTER TABLE field_verifications
    ADD COLUMN IF NOT EXISTS source_version VARCHAR(80);
ALTER TABLE field_verifications
    ADD COLUMN IF NOT EXISTS source_record_id VARCHAR(100);
ALTER TABLE field_verifications
    ADD COLUMN IF NOT EXISTS source_checksum_sha256 VARCHAR(64);
ALTER TABLE field_verifications
    ADD COLUMN IF NOT EXISTS import_batch_code VARCHAR(80);
ALTER TABLE field_verifications
    ADD COLUMN IF NOT EXISTS imported_by VARCHAR(100);
ALTER TABLE field_verifications
    ADD COLUMN IF NOT EXISTS imported_by_code VARCHAR(50);
ALTER TABLE field_verifications
    ADD COLUMN IF NOT EXISTS imported_by_role VARCHAR(40);

CREATE UNIQUE INDEX IF NOT EXISTS idx_field_verifications_source_record
    ON field_verifications (task_id, source_name, source_record_id)
    WHERE source_record_id IS NOT NULL;

-- 清理旧初始化脚本生成的四条虚构 GPS、照片和语音记录及其问题审计。
DELETE FROM quality_issues
WHERE rule_code IN (
    'FIELD_FV-2026-001',
    'FIELD_FV-2026-002',
    'FIELD_FV-2026-003',
    'FIELD_FV-2026-004'
);

DELETE FROM review_records
WHERE review_level = 'field_verification'
  AND (
      comment LIKE '%FV-2026-001%'
      OR comment LIKE '%FV-2026-002%'
      OR comment LIKE '%FV-2026-003%'
      OR comment LIKE '%FV-2026-004%'
  );

DELETE FROM field_verifications
WHERE verification_code IN (
    'FV-2026-001',
    'FV-2026-002',
    'FV-2026-003',
    'FV-2026-004'
)
  AND source_name IS NULL;

COMMIT;
