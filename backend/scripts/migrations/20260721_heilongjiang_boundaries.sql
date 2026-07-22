-- 将行政区划表升级为支持省、市、县区三级真实 MultiPolygon 边界。
-- 执行本迁移后，使用以下命令导入版本化数据快照：
-- poetry run python -m scripts.import_administrative_boundaries

BEGIN;

ALTER TABLE administrative_boundaries
    ADD COLUMN IF NOT EXISTS parent_code VARCHAR(50);
ALTER TABLE administrative_boundaries
    ADD COLUMN IF NOT EXISTS source_name VARCHAR(120);
ALTER TABLE administrative_boundaries
    ADD COLUMN IF NOT EXISTS source_uri VARCHAR(500);
ALTER TABLE administrative_boundaries
    ADD COLUMN IF NOT EXISTS source_version VARCHAR(80);
ALTER TABLE administrative_boundaries
    ADD COLUMN IF NOT EXISTS source_updated_at DATE;
ALTER TABLE administrative_boundaries
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

UPDATE administrative_boundaries
SET source_name = '未标注历史数据'
WHERE source_name IS NULL;

ALTER TABLE administrative_boundaries
    ALTER COLUMN source_name SET NOT NULL;
ALTER TABLE administrative_boundaries
    ALTER COLUMN geom TYPE GEOMETRY(MULTIPOLYGON, 4326)
    USING ST_Multi(geom);

COMMIT;
