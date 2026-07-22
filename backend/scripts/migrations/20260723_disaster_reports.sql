-- 新增灾害监测专题报告实体、来源快照和当前版本状态。
CREATE TABLE IF NOT EXISTS disaster_reports (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    report_code VARCHAR(100) NOT NULL,
    report_title VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL,
    file_uri VARCHAR(500) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    source_patch_count INTEGER NOT NULL,
    source_confirmed_count INTEGER NOT NULL,
    source_excluded_count INTEGER NOT NULL,
    source_latest_updated_at TIMESTAMPTZ NOT NULL,
    affected_area_ha NUMERIC(14, 4) NOT NULL,
    report_manifest JSONB NOT NULL,
    generation_comment TEXT NOT NULL,
    generated_by VARCHAR(100) NOT NULL,
    generated_by_code VARCHAR(50) NOT NULL,
    generated_by_role VARCHAR(40) NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_disaster_report_code UNIQUE (report_code),
    CONSTRAINT ck_disaster_report_status
        CHECK (status IN ('completed', 'superseded', 'invalid')),
    CONSTRAINT ck_disaster_report_file_evidence
        CHECK (file_size_bytes > 0 AND char_length(checksum_sha256) = 64),
    CONSTRAINT ck_disaster_report_source_counts
        CHECK (
            source_patch_count >= 0
            AND source_confirmed_count >= 0
            AND source_excluded_count >= 0
        )
);

CREATE INDEX IF NOT EXISTS idx_disaster_reports_task_generated
    ON disaster_reports (task_id, generated_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_disaster_reports_current_task
    ON disaster_reports (task_id)
    WHERE status = 'completed';
