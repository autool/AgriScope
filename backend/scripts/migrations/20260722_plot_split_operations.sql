-- 增加地块分割、合并和恢复共用的操作日志，为版本审计及后续撤销/重做提供依据。
CREATE TABLE IF NOT EXISTS plot_edit_operations (
    id SERIAL PRIMARY KEY,
    operation_code VARCHAR(80) NOT NULL UNIQUE,
    task_id INTEGER NOT NULL
        REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    operation_type VARCHAR(30) NOT NULL,
    source_plot_codes JSONB NOT NULL,
    result_plot_codes JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'applied',
    operator VARCHAR(100) NOT NULL,
    operator_code VARCHAR(50) NOT NULL,
    operator_role VARCHAR(40) NOT NULL,
    comment VARCHAR(500) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reverted_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_plot_edit_operations_task_created
    ON plot_edit_operations (task_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_plot_edit_operations_source_codes
    ON plot_edit_operations USING GIN (source_plot_codes);

CREATE INDEX IF NOT EXISTS idx_plot_edit_operations_result_codes
    ON plot_edit_operations USING GIN (result_plot_codes);
