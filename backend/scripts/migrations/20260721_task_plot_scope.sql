BEGIN;

-- 质量检查和审核门禁必须以任务实际分配图斑为准，不能统计全库有效图斑。
CREATE TABLE IF NOT EXISTS task_plots (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL
        REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    plot_code VARCHAR(50) NOT NULL
        REFERENCES farmland_plots(plot_code) ON DELETE CASCADE,
    assigned_by VARCHAR(100) NOT NULL,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_task_plot UNIQUE (task_id, plot_code)
);

CREATE INDEX IF NOT EXISTS idx_task_plots_task
    ON task_plots (task_id);

CREATE INDEX IF NOT EXISTS idx_task_plots_plot
    ON task_plots (plot_code);

INSERT INTO task_plots (task_id, plot_code, assigned_by)
SELECT task.id, plot.plot_code, '任务图斑作用域迁移'
FROM monitoring_tasks AS task
JOIN farmland_plots AS plot
  ON plot.interpretation_status != 'deleted'
WHERE task.task_code = 'RS-2026-045'
ON CONFLICT (task_id, plot_code) DO NOTHING;

UPDATE monitoring_tasks AS task
SET total_plots = summary.total_plots,
    completed_plots = summary.completed_plots,
    updated_at = NOW()
FROM (
    SELECT
        scope.task_id,
        COUNT(*) FILTER (
            WHERE plot.interpretation_status != 'deleted'
        ) AS total_plots,
        COUNT(*) FILTER (
            WHERE plot.interpretation_status = 'interpreted'
        ) AS completed_plots
    FROM task_plots AS scope
    JOIN farmland_plots AS plot ON plot.plot_code = scope.plot_code
    GROUP BY scope.task_id
) AS summary
WHERE task.id = summary.task_id;

COMMIT;
