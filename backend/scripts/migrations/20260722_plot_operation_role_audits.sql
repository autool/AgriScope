BEGIN;

-- 地块版本和任务分配补充稳定用户编码及执行时角色快照，
-- 解决自由文本姓名无法作为授权与审计依据的问题。
ALTER TABLE plot_versions
    ADD COLUMN IF NOT EXISTS created_by_code VARCHAR(50);
ALTER TABLE plot_versions
    ADD COLUMN IF NOT EXISTS created_by_role VARCHAR(40);
ALTER TABLE task_plots
    ADD COLUMN IF NOT EXISTS assigned_by_code VARCHAR(50);
ALTER TABLE task_plots
    ADD COLUMN IF NOT EXISTS assigned_by_role VARCHAR(40);

UPDATE plot_versions AS version
SET created_by_code = project_user.user_code,
    created_by_role = project_user.role_code
FROM farmland_plots AS plot,
     task_plots AS scope,
     monitoring_tasks AS task,
     project_users AS project_user
WHERE version.plot_code = plot.plot_code
  AND scope.plot_code = plot.plot_code
  AND task.id = scope.task_id
  AND project_user.project_id = task.project_id
  AND project_user.display_name = version.created_by
  AND version.created_by_code IS NULL;

UPDATE task_plots AS scope
SET assigned_by_code = project_user.user_code,
    assigned_by_role = project_user.role_code
FROM monitoring_tasks AS task,
     project_users AS project_user
WHERE task.id = scope.task_id
  AND project_user.project_id = task.project_id
  AND project_user.display_name = scope.assigned_by
  AND scope.assigned_by_code IS NULL;

-- 系统导入与历史作用域迁移不对应人工项目成员，使用固定系统身份补齐审计。
UPDATE plot_versions
SET created_by_code = CASE created_by
        WHEN 'OpenStreetMap 数据导入程序' THEN 'system_osm_import'
        WHEN '系统初始化' THEN 'system_init'
        ELSE created_by_code
    END,
    created_by_role = 'system'
WHERE created_by_code IS NULL
  AND created_by IN ('OpenStreetMap 数据导入程序', '系统初始化');

UPDATE task_plots
SET assigned_by_code = CASE assigned_by
        WHEN 'OpenStreetMap 数据导入程序' THEN 'system_osm_import'
        WHEN '任务图斑作用域迁移' THEN 'system_task_scope_migration'
        ELSE assigned_by_code
    END,
    assigned_by_role = 'system'
WHERE assigned_by_code IS NULL
  AND assigned_by IN ('OpenStreetMap 数据导入程序', '任务图斑作用域迁移');

COMMIT;
