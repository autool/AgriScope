-- 新增面积统计正式报告包：服务端生成 XLSX、PDF 和 manifest，
-- 以 ZIP 实体、任务图斑和历史快照状态实现版本与失效审计。

CREATE TABLE IF NOT EXISTS statistics_reports (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    report_code VARCHAR(100) NOT NULL UNIQUE,
    report_title VARCHAR(200) NOT NULL,
    version INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    bundle_uri VARCHAR(500) NOT NULL,
    bundle_size_bytes BIGINT NOT NULL,
    bundle_checksum_sha256 VARCHAR(64) NOT NULL,
    xlsx_size_bytes BIGINT NOT NULL,
    xlsx_checksum_sha256 VARCHAR(64) NOT NULL,
    pdf_size_bytes BIGINT NOT NULL,
    pdf_checksum_sha256 VARCHAR(64) NOT NULL,
    task_plot_count INTEGER NOT NULL,
    task_updated_at_snapshot TIMESTAMPTZ NOT NULL,
    history_snapshot_count INTEGER NOT NULL,
    history_latest_updated_at TIMESTAMPTZ,
    report_manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
    generation_comment TEXT NOT NULL,
    generated_by VARCHAR(100) NOT NULL,
    generated_by_code VARCHAR(50) NOT NULL,
    generated_by_role VARCHAR(40) NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_statistics_report_task_version UNIQUE (task_id, version),
    CONSTRAINT ck_statistics_report_status CHECK (
        status IN ('completed', 'superseded', 'invalid')
    ),
    CONSTRAINT ck_statistics_report_file_sizes CHECK (
        bundle_size_bytes > 0
        AND xlsx_size_bytes > 0
        AND pdf_size_bytes > 0
    ),
    CONSTRAINT ck_statistics_report_checksums CHECK (
        char_length(bundle_checksum_sha256) = 64
        AND char_length(xlsx_checksum_sha256) = 64
        AND char_length(pdf_checksum_sha256) = 64
    ),
    CONSTRAINT ck_statistics_report_source_counts CHECK (
        task_plot_count >= 0 AND history_snapshot_count >= 0
    )
);

CREATE INDEX IF NOT EXISTS idx_statistics_reports_task_version
    ON statistics_reports (task_id, version DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_statistics_reports_current_task
    ON statistics_reports (task_id)
    WHERE status = 'completed';
