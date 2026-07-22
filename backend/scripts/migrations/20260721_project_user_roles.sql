BEGIN;

CREATE TABLE IF NOT EXISTS project_users (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL
        REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    user_code VARCHAR(50) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    role_code VARCHAR(40) NOT NULL,
    role_name VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_project_user_code UNIQUE (project_id, user_code),
    CONSTRAINT ck_project_user_status CHECK (status IN ('active', 'disabled'))
);

CREATE INDEX IF NOT EXISTS idx_project_users_project_role
    ON project_users (project_id, role_code, status);

ALTER TABLE review_records ADD COLUMN IF NOT EXISTS reviewer_code VARCHAR(50);
ALTER TABLE review_records ADD COLUMN IF NOT EXISTS reviewer_role VARCHAR(40);

INSERT INTO project_users (
    project_id, user_code, display_name, role_code, role_name,
    status, is_default
)
SELECT project.id, seed.user_code, seed.display_name, seed.role_code,
       seed.role_name, 'active', seed.is_default
FROM monitoring_projects AS project
CROSS JOIN (
    VALUES
        ('interp-li-jing', '李静', 'interpreter', '内业解译员', TRUE),
        ('field-zhang-qiang', '张强', 'field_inspector', '外业核查员', FALSE),
        ('quality-wang-haifeng', '王海峰', 'quality_inspector', '质检员', FALSE),
        ('manager-zhao-zhiyuan', '赵志远', 'project_manager', '项目负责人', FALSE),
        ('client-agri-dept', '农业农村厅审核代表', 'client_reviewer', '甲方（监管方）', FALSE)
) AS seed(user_code, display_name, role_code, role_name, is_default)
WHERE project.project_code = 'RS-2026'
ON CONFLICT (project_id, user_code) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    role_code = EXCLUDED.role_code,
    role_name = EXCLUDED.role_name,
    status = EXCLUDED.status,
    is_default = EXCLUDED.is_default,
    updated_at = NOW();

UPDATE review_records AS record
SET reviewer_code = project_user.user_code,
    reviewer_role = project_user.role_code
FROM monitoring_tasks AS task
JOIN project_users AS project_user
  ON project_user.project_id = task.project_id
WHERE record.task_id = task.id
  AND project_user.display_name = record.reviewer
  AND record.reviewer_code IS NULL;

COMMIT;
