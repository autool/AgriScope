-- 扩展影像资产表，保存真实文件、栅格结构、CRS、范围和校验和元数据。

BEGIN;

ALTER TABLE imagery_assets ADD COLUMN IF NOT EXISTS original_filename VARCHAR(255);
ALTER TABLE imagery_assets
    ADD COLUMN IF NOT EXISTS data_status VARCHAR(20) NOT NULL DEFAULT 'operational';
ALTER TABLE imagery_assets ADD COLUMN IF NOT EXISTS file_uri VARCHAR(500);
ALTER TABLE imagery_assets ADD COLUMN IF NOT EXISTS file_format VARCHAR(30);
ALTER TABLE imagery_assets ADD COLUMN IF NOT EXISTS file_size_bytes BIGINT;
ALTER TABLE imagery_assets ADD COLUMN IF NOT EXISTS checksum_sha256 VARCHAR(64);
ALTER TABLE imagery_assets ADD COLUMN IF NOT EXISTS band_count INTEGER;
ALTER TABLE imagery_assets ADD COLUMN IF NOT EXISTS raster_width INTEGER;
ALTER TABLE imagery_assets ADD COLUMN IF NOT EXISTS raster_height INTEGER;
ALTER TABLE imagery_assets ADD COLUMN IF NOT EXISTS crs VARCHAR(100);
ALTER TABLE imagery_assets
    ADD COLUMN IF NOT EXISTS raster_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE imagery_assets ADD COLUMN IF NOT EXISTS imported_by VARCHAR(100);

CREATE UNIQUE INDEX IF NOT EXISTS idx_imagery_assets_checksum
    ON imagery_assets (checksum_sha256)
    WHERE checksum_sha256 IS NOT NULL;

UPDATE imagery_assets
SET data_status = 'demo'
WHERE asset_code LIKE 'DEMO-%'
   OR asset_name LIKE '%明确演示%';

COMMIT;
