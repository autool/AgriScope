-- 为图斑分割/合并的多次撤销与重做保存不可变事件审计。
ALTER TABLE plot_edit_operations
    ADD COLUMN IF NOT EXISTS applied_versions JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE plot_edit_operations
    ADD COLUMN IF NOT EXISTS reverted_versions JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS plot_edit_operation_events (
    id SERIAL PRIMARY KEY,
    event_code VARCHAR(80) NOT NULL UNIQUE,
    operation_id INTEGER NOT NULL
        REFERENCES plot_edit_operations(id) ON DELETE CASCADE,
    action VARCHAR(20) NOT NULL,
    operator VARCHAR(100) NOT NULL,
    operator_code VARCHAR(50) NOT NULL,
    operator_role VARCHAR(40) NOT NULL,
    comment VARCHAR(500) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_plot_edit_operation_events_operation
    ON plot_edit_operation_events (operation_id, created_at DESC);
