BEGIN;

ALTER TABLE quality_issues ADD COLUMN IF NOT EXISTS resolved_by VARCHAR(100);
ALTER TABLE quality_issues ADD COLUMN IF NOT EXISTS resolved_by_code VARCHAR(50);
ALTER TABLE quality_issues ADD COLUMN IF NOT EXISTS resolved_by_role VARCHAR(40);
ALTER TABLE quality_issues ADD COLUMN IF NOT EXISTS resolution_comment VARCHAR(1000);

COMMIT;
