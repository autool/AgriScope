BEGIN;

ALTER TABLE project_rule_configs
    ADD COLUMN IF NOT EXISTS updated_by_code VARCHAR(50);
ALTER TABLE project_rule_configs
    ADD COLUMN IF NOT EXISTS updated_by_role VARCHAR(40);
ALTER TABLE project_rule_config_audits
    ADD COLUMN IF NOT EXISTS operator_code VARCHAR(50);
ALTER TABLE project_rule_config_audits
    ADD COLUMN IF NOT EXISTS operator_role VARCHAR(40);

ALTER TABLE field_verifications
    ADD COLUMN IF NOT EXISTS investigator_code VARCHAR(50);
ALTER TABLE field_verifications
    ADD COLUMN IF NOT EXISTS resolved_by VARCHAR(100);
ALTER TABLE field_verifications
    ADD COLUMN IF NOT EXISTS resolved_by_code VARCHAR(50);
ALTER TABLE field_verifications
    ADD COLUMN IF NOT EXISTS resolved_by_role VARCHAR(40);

ALTER TABLE disaster_patches ADD COLUMN IF NOT EXISTS reviewed_by VARCHAR(100);
ALTER TABLE disaster_patches ADD COLUMN IF NOT EXISTS reviewed_by_code VARCHAR(50);
ALTER TABLE disaster_patches ADD COLUMN IF NOT EXISTS reviewed_by_role VARCHAR(40);
ALTER TABLE disaster_patches ADD COLUMN IF NOT EXISTS review_comment VARCHAR(1000);
ALTER TABLE disaster_patches ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;

UPDATE project_rule_configs AS config
SET updated_by_code = project_user.user_code,
    updated_by_role = project_user.role_code
FROM project_users AS project_user
WHERE project_user.project_id = config.project_id
  AND project_user.display_name = config.updated_by
  AND config.updated_by_code IS NULL;

UPDATE project_rule_config_audits AS audit
SET operator_code = project_user.user_code,
    operator_role = project_user.role_code
FROM project_users AS project_user
WHERE project_user.project_id = audit.project_id
  AND project_user.display_name = audit.operator
  AND audit.operator_code IS NULL;

UPDATE field_verifications AS field_record
SET investigator_code = project_user.user_code
FROM monitoring_tasks AS task
JOIN project_users AS project_user
  ON project_user.project_id = task.project_id
WHERE field_record.task_id = task.id
  AND project_user.display_name = field_record.investigator
  AND field_record.investigator_code IS NULL;

WITH latest_field_review AS (
    SELECT DISTINCT ON (field_record.id)
        field_record.id AS field_id,
        review.reviewer,
        review.reviewer_code,
        review.reviewer_role
    FROM field_verifications AS field_record
    JOIN review_records AS review
      ON review.task_id = field_record.task_id
     AND review.action = 'field_issue_resolved'
     AND review.comment LIKE field_record.verification_code || ':%'
    ORDER BY field_record.id, review.created_at DESC
)
UPDATE field_verifications AS field_record
SET resolved_by = latest.reviewer,
    resolved_by_code = latest.reviewer_code,
    resolved_by_role = latest.reviewer_role
FROM latest_field_review AS latest
WHERE field_record.id = latest.field_id
  AND field_record.resolved_by IS NULL;

WITH latest_disaster_review AS (
    SELECT DISTINCT ON (patch.id)
        patch.id AS patch_id,
        review.reviewer,
        review.reviewer_code,
        review.reviewer_role,
        review.comment,
        review.created_at
    FROM disaster_patches AS patch
    JOIN review_records AS review
      ON review.task_id = patch.task_id
     AND review.action = 'disaster_patch_updated'
     AND review.comment LIKE patch.patch_code || ':%'
    ORDER BY patch.id, review.created_at DESC
)
UPDATE disaster_patches AS patch
SET reviewed_by = latest.reviewer,
    reviewed_by_code = latest.reviewer_code,
    reviewed_by_role = latest.reviewer_role,
    review_comment = latest.comment,
    reviewed_at = latest.created_at
FROM latest_disaster_review AS latest
WHERE patch.id = latest.patch_id
  AND patch.reviewed_by IS NULL;

COMMIT;
