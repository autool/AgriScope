-- 新增绑定当前成果交付包的版本化正式验收报告。
-- 报告包真实包含 DOCX、PDF 和 manifest，并保存任务、成果包、质量摘要及用户角色快照。

CREATE TABLE IF NOT EXISTS acceptance_reports (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    delivery_package_id INTEGER NOT NULL
        REFERENCES delivery_packages(id) ON DELETE RESTRICT,
    report_code VARCHAR(110) NOT NULL UNIQUE,
    report_title VARCHAR(200) NOT NULL,
    version INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    bundle_uri VARCHAR(500) NOT NULL,
    bundle_size_bytes BIGINT NOT NULL,
    bundle_checksum_sha256 VARCHAR(64) NOT NULL,
    docx_filename VARCHAR(160) NOT NULL,
    docx_size_bytes BIGINT NOT NULL,
    docx_checksum_sha256 VARCHAR(64) NOT NULL,
    pdf_filename VARCHAR(160) NOT NULL,
    pdf_size_bytes BIGINT NOT NULL,
    pdf_checksum_sha256 VARCHAR(64) NOT NULL,
    task_plot_count INTEGER NOT NULL,
    task_updated_at_snapshot TIMESTAMPTZ NOT NULL,
    delivery_package_code VARCHAR(80) NOT NULL,
    delivery_package_completed_at_snapshot TIMESTAMPTZ NOT NULL,
    delivery_package_size_bytes BIGINT NOT NULL,
    delivery_package_checksum_sha256 VARCHAR(64) NOT NULL,
    delivery_manifest_count INTEGER NOT NULL,
    quality_summary_checksum_sha256 VARCHAR(64) NOT NULL,
    report_manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
    generation_comment TEXT NOT NULL,
    generated_by VARCHAR(100) NOT NULL,
    generated_by_code VARCHAR(50) NOT NULL,
    generated_by_role VARCHAR(40) NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_acceptance_report_task_version UNIQUE (task_id, version),
    CONSTRAINT ck_acceptance_report_status CHECK (
        status IN ('completed', 'superseded', 'invalid')
    ),
    CONSTRAINT ck_acceptance_report_file_sizes CHECK (
        bundle_size_bytes > 0
        AND docx_size_bytes > 0
        AND pdf_size_bytes > 0
    ),
    CONSTRAINT ck_acceptance_report_checksums CHECK (
        char_length(bundle_checksum_sha256) = 64
        AND char_length(docx_checksum_sha256) = 64
        AND char_length(pdf_checksum_sha256) = 64
        AND char_length(delivery_package_checksum_sha256) = 64
        AND char_length(quality_summary_checksum_sha256) = 64
    ),
    CONSTRAINT ck_acceptance_report_source_counts CHECK (
        task_plot_count >= 0 AND delivery_manifest_count >= 0
    )
);

CREATE INDEX IF NOT EXISTS idx_acceptance_reports_task_version
    ON acceptance_reports (task_id, version DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_acceptance_reports_current_task
    ON acceptance_reports (task_id)
    WHERE status = 'completed';
