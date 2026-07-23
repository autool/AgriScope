-- 新增任务级全量质检不可变批次账本。
-- 每次运行保存任务图斑快照、项目规则版本、活动自定义字段模式、
-- 逐规则汇总、稳定操作人和耗时，避免质检证据只存在于瞬时 API 响应。

CREATE TABLE IF NOT EXISTS task_quality_runs (
    id SERIAL PRIMARY KEY,
    run_code VARCHAR(80) NOT NULL UNIQUE,
    task_id INTEGER NOT NULL REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    task_plot_count INTEGER NOT NULL,
    task_updated_at_snapshot TIMESTAMPTZ NOT NULL,
    rule_config_version INTEGER NOT NULL,
    rule_config_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    custom_field_schema_digest VARCHAR(64) NOT NULL,
    custom_field_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
    checked_plot_count INTEGER NOT NULL,
    passing_plot_count INTEGER NOT NULL,
    failed_plot_count INTEGER NOT NULL,
    average_score NUMERIC(5, 2),
    issue_count INTEGER NOT NULL,
    can_submit BOOLEAN NOT NULL,
    duration_ms INTEGER NOT NULL,
    rule_summaries JSONB NOT NULL DEFAULT '[]'::jsonb,
    operator VARCHAR(100) NOT NULL,
    operator_code VARCHAR(50) NOT NULL,
    operator_role VARCHAR(40) NOT NULL,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_task_quality_run_non_negative CHECK (
        task_plot_count >= 0
        AND checked_plot_count >= 0
        AND passing_plot_count >= 0
        AND failed_plot_count >= 0
        AND issue_count >= 0
        AND duration_ms >= 0
    ),
    CONSTRAINT ck_task_quality_run_checked_balance CHECK (
        checked_plot_count = passing_plot_count + failed_plot_count
    ),
    CONSTRAINT ck_task_quality_run_full_coverage CHECK (
        task_plot_count = checked_plot_count
    ),
    CONSTRAINT ck_task_quality_run_rule_version CHECK (
        rule_config_version >= 1
    ),
    CONSTRAINT ck_task_quality_run_schema_digest CHECK (
        char_length(custom_field_schema_digest) = 64
    )
);

CREATE INDEX IF NOT EXISTS idx_task_quality_runs_task_created
    ON task_quality_runs (task_id, created_at DESC);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_task_quality_run_full_coverage'
    ) THEN
        ALTER TABLE task_quality_runs
            ADD CONSTRAINT ck_task_quality_run_full_coverage
            CHECK (task_plot_count = checked_plot_count);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_task_quality_run_rule_version'
    ) THEN
        ALTER TABLE task_quality_runs
            ADD CONSTRAINT ck_task_quality_run_rule_version
            CHECK (rule_config_version >= 1);
    END IF;
END
$$;
