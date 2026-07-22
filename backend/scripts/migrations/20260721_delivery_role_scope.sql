BEGIN;

ALTER TABLE delivery_packages
    ADD COLUMN IF NOT EXISTS generated_by_code VARCHAR(50);
ALTER TABLE delivery_packages
    ADD COLUMN IF NOT EXISTS generated_by_role VARCHAR(40);

UPDATE delivery_packages AS package
SET generated_by_code = project_user.user_code,
    generated_by_role = project_user.role_code
FROM monitoring_tasks AS task
JOIN project_users AS project_user
  ON project_user.project_id = task.project_id
WHERE package.task_id = task.id
  AND project_user.display_name = package.generated_by
  AND package.generated_by_code IS NULL;

UPDATE delivery_packages AS package
SET status = 'superseded'
FROM monitoring_tasks AS task
WHERE package.task_id = task.id
  AND package.status = 'completed'
  AND (
      package.completed_at < task.updated_at
      OR COALESCE((package.quality_summary ->> 'plot_count')::INTEGER, -1)
         <> task.total_plots
  );

COMMIT;
