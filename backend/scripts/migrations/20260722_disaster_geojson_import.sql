BEGIN;

-- 灾害斑块补充模型来源、批次校验和稳定用户审计，支持真实 GeoJSON 导入。
ALTER TABLE disaster_patches
    ALTER COLUMN source TYPE VARCHAR(120);
ALTER TABLE disaster_patches
    ADD COLUMN IF NOT EXISTS source_uri VARCHAR(500);
ALTER TABLE disaster_patches
    ADD COLUMN IF NOT EXISTS source_version VARCHAR(80);
ALTER TABLE disaster_patches
    ADD COLUMN IF NOT EXISTS source_feature_id VARCHAR(100);
ALTER TABLE disaster_patches
    ADD COLUMN IF NOT EXISTS source_checksum_sha256 VARCHAR(64);
ALTER TABLE disaster_patches
    ADD COLUMN IF NOT EXISTS import_batch_code VARCHAR(80);
ALTER TABLE disaster_patches
    ADD COLUMN IF NOT EXISTS imported_by VARCHAR(100);
ALTER TABLE disaster_patches
    ADD COLUMN IF NOT EXISTS imported_by_code VARCHAR(50);
ALTER TABLE disaster_patches
    ADD COLUMN IF NOT EXISTS imported_by_role VARCHAR(40);

CREATE UNIQUE INDEX IF NOT EXISTS idx_disaster_patches_source_feature
    ON disaster_patches (task_id, source, source_feature_id)
    WHERE source_feature_id IS NOT NULL;

-- 清理旧初始化脚本生成的三个规则矩形，避免将无来源实体成果当作真实灾害数据。
DELETE FROM disaster_patches
WHERE patch_code IN ('DS-2026-001', 'DS-2026-002', 'DS-2026-003')
  AND source IN (
      'Sentinel-2 洪涝模型',
      'GF2 NDVI 异常检测',
      '多时相长势模型'
  )
  AND source_uri IS NULL;

COMMIT;
