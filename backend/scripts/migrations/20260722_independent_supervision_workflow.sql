-- 独立项目监理首个可交付闭环。
-- 与自动质检、内业自检、质检审核和甲方复核分离，保存真实抽样与不可变证据。

CREATE TABLE IF NOT EXISTS supervision_plans (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL
        REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    task_id INTEGER NOT NULL
        REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    plan_code VARCHAR(80) NOT NULL UNIQUE,
    plan_name VARCHAR(200) NOT NULL,
    sampling_method VARCHAR(30) NOT NULL,
    sample_ratio NUMERIC(7, 4) NOT NULL,
    minimum_per_region INTEGER NOT NULL,
    region_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    task_plot_count_snapshot INTEGER NOT NULL,
    task_updated_at_snapshot TIMESTAMPTZ NOT NULL,
    planned_start_date DATE NOT NULL,
    planned_end_date DATE NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    created_by VARCHAR(100) NOT NULL,
    created_by_code VARCHAR(50) NOT NULL,
    created_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_supervision_plan_sampling_method CHECK (
        sampling_method IN ('systematic', 'stratified_random')
    ),
    CONSTRAINT ck_supervision_plan_ratio CHECK (
        sample_ratio >= 0.1 AND sample_ratio <= 100
    ),
    CONSTRAINT ck_supervision_plan_minimum CHECK (
        minimum_per_region >= 1 AND minimum_per_region <= 500
    ),
    CONSTRAINT ck_supervision_plan_task_count CHECK (
        task_plot_count_snapshot > 0
    ),
    CONSTRAINT ck_supervision_plan_dates CHECK (
        planned_end_date >= planned_start_date
    ),
    CONSTRAINT ck_supervision_plan_status CHECK (
        status IN ('active', 'completed', 'cancelled')
    )
);

CREATE INDEX IF NOT EXISTS idx_supervision_plans_task_status
    ON supervision_plans (task_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS supervision_samples (
    id SERIAL PRIMARY KEY,
    plan_id INTEGER NOT NULL
        REFERENCES supervision_plans(id) ON DELETE CASCADE,
    plot_code VARCHAR(50) NOT NULL
        REFERENCES farmland_plots(plot_code) ON DELETE RESTRICT,
    region_code VARCHAR(50) NOT NULL,
    region_name VARCHAR(100) NOT NULL,
    plot_version_snapshot INTEGER NOT NULL,
    selection_rank INTEGER NOT NULL,
    selected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_supervision_sample_plot UNIQUE (plan_id, plot_code),
    CONSTRAINT ck_supervision_sample_version CHECK (plot_version_snapshot > 0),
    CONSTRAINT ck_supervision_sample_rank CHECK (selection_rank > 0)
);

CREATE INDEX IF NOT EXISTS idx_supervision_samples_plan_region
    ON supervision_samples (plan_id, region_code, selection_rank);
CREATE INDEX IF NOT EXISTS idx_supervision_samples_plot
    ON supervision_samples (plot_code);

CREATE TABLE IF NOT EXISTS supervision_inspections (
    id SERIAL PRIMARY KEY,
    plan_id INTEGER NOT NULL
        REFERENCES supervision_plans(id) ON DELETE CASCADE,
    inspection_code VARCHAR(80) NOT NULL,
    inspection_stage VARCHAR(40) NOT NULL,
    inspected_at TIMESTAMPTZ NOT NULL,
    conclusion VARCHAR(30) NOT NULL,
    evidence_uri VARCHAR(500) NOT NULL,
    summary TEXT NOT NULL,
    inspector VARCHAR(100) NOT NULL,
    inspector_code VARCHAR(50) NOT NULL,
    inspector_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_supervision_inspection_code UNIQUE (
        plan_id, inspection_code
    ),
    CONSTRAINT ck_supervision_inspection_stage CHECK (
        inspection_stage IN (
            'imagery_processing',
            'plot_interpretation',
            'quality_control',
            'field_verification',
            'review_delivery'
        )
    ),
    CONSTRAINT ck_supervision_inspection_conclusion CHECK (
        conclusion IN ('passed', 'conditional', 'failed')
    )
);

CREATE INDEX IF NOT EXISTS idx_supervision_inspections_plan_time
    ON supervision_inspections (plan_id, inspected_at DESC);

CREATE TABLE IF NOT EXISTS supervision_findings (
    id SERIAL PRIMARY KEY,
    inspection_id INTEGER NOT NULL
        REFERENCES supervision_inspections(id) ON DELETE CASCADE,
    sample_id INTEGER
        REFERENCES supervision_samples(id) ON DELETE SET NULL,
    finding_code VARCHAR(80) NOT NULL,
    region_code VARCHAR(50) NOT NULL,
    region_name VARCHAR(100) NOT NULL,
    issue_type VARCHAR(60) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    description TEXT NOT NULL,
    evidence_uri VARCHAR(500) NOT NULL,
    rework_deadline DATE NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'open',
    rectification_comment TEXT,
    rectification_evidence_uri VARCHAR(500),
    rectified_by VARCHAR(100),
    rectified_by_code VARCHAR(50),
    rectified_by_role VARCHAR(40),
    rectified_at TIMESTAMPTZ,
    created_by VARCHAR(100) NOT NULL,
    created_by_code VARCHAR(50) NOT NULL,
    created_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_supervision_finding_code UNIQUE (
        inspection_id, finding_code
    ),
    CONSTRAINT ck_supervision_finding_severity CHECK (
        severity IN ('minor', 'major', 'critical')
    ),
    CONSTRAINT ck_supervision_finding_status CHECK (
        status IN (
            'open',
            'rectification_submitted',
            'rework_required',
            'closed'
        )
    ),
    CONSTRAINT ck_supervision_finding_rectification CHECK (
        status = 'open'
        OR (
            rectification_comment IS NOT NULL
            AND rectification_evidence_uri IS NOT NULL
            AND rectified_by_code IS NOT NULL
            AND rectified_at IS NOT NULL
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_supervision_findings_status_deadline
    ON supervision_findings (status, rework_deadline);
CREATE INDEX IF NOT EXISTS idx_supervision_findings_region
    ON supervision_findings (region_code, severity, status);

CREATE TABLE IF NOT EXISTS supervision_reinspections (
    id SERIAL PRIMARY KEY,
    finding_id INTEGER NOT NULL
        REFERENCES supervision_findings(id) ON DELETE CASCADE,
    round_no INTEGER NOT NULL,
    result VARCHAR(20) NOT NULL,
    comment TEXT NOT NULL,
    evidence_uri VARCHAR(500) NOT NULL,
    inspector VARCHAR(100) NOT NULL,
    inspector_code VARCHAR(50) NOT NULL,
    inspector_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_supervision_reinspection_round UNIQUE (
        finding_id, round_no
    ),
    CONSTRAINT ck_supervision_reinspection_round CHECK (round_no > 0),
    CONSTRAINT ck_supervision_reinspection_result CHECK (
        result IN ('passed', 'failed')
    )
);

CREATE INDEX IF NOT EXISTS idx_supervision_reinspections_finding_time
    ON supervision_reinspections (finding_id, round_no);

CREATE TABLE IF NOT EXISTS supervision_county_evaluations (
    id SERIAL PRIMARY KEY,
    plan_id INTEGER NOT NULL
        REFERENCES supervision_plans(id) ON DELETE CASCADE,
    region_code VARCHAR(50) NOT NULL,
    region_name VARCHAR(100) NOT NULL,
    quality_score NUMERIC(5, 2) NOT NULL,
    timeliness_score NUMERIC(5, 2) NOT NULL,
    compliance_score NUMERIC(5, 2) NOT NULL,
    overall_score NUMERIC(5, 2) NOT NULL,
    grade VARCHAR(20) NOT NULL,
    comment TEXT NOT NULL,
    evaluated_by VARCHAR(100) NOT NULL,
    evaluated_by_code VARCHAR(50) NOT NULL,
    evaluated_by_role VARCHAR(40) NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_supervision_county_evaluation UNIQUE (
        plan_id, region_code
    ),
    CONSTRAINT ck_supervision_county_scores CHECK (
        quality_score >= 0 AND quality_score <= 100
        AND timeliness_score >= 0 AND timeliness_score <= 100
        AND compliance_score >= 0 AND compliance_score <= 100
        AND overall_score >= 0 AND overall_score <= 100
    ),
    CONSTRAINT ck_supervision_county_grade CHECK (
        grade IN ('A', 'B', 'C', 'D')
    )
);

CREATE INDEX IF NOT EXISTS idx_supervision_county_plan_grade
    ON supervision_county_evaluations (plan_id, grade, overall_score);

CREATE TABLE IF NOT EXISTS supervision_reports (
    id SERIAL PRIMARY KEY,
    plan_id INTEGER NOT NULL UNIQUE
        REFERENCES supervision_plans(id) ON DELETE RESTRICT,
    report_code VARCHAR(100) NOT NULL UNIQUE,
    file_uri VARCHAR(500) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    evidence_manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
    generated_by VARCHAR(100) NOT NULL,
    generated_by_code VARCHAR(50) NOT NULL,
    generated_by_role VARCHAR(40) NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_supervision_report_size CHECK (file_size_bytes > 0),
    CONSTRAINT ck_supervision_report_checksum CHECK (
        char_length(checksum_sha256) = 64
    )
);

CREATE TABLE IF NOT EXISTS supervision_events (
    id SERIAL PRIMARY KEY,
    plan_id INTEGER NOT NULL
        REFERENCES supervision_plans(id) ON DELETE CASCADE,
    entity_type VARCHAR(40) NOT NULL,
    entity_code VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    previous_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    new_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    comment TEXT NOT NULL,
    operator VARCHAR(100) NOT NULL,
    operator_code VARCHAR(50) NOT NULL,
    operator_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_supervision_events_plan_time
    ON supervision_events (plan_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_supervision_events_entity
    ON supervision_events (entity_type, entity_code, created_at DESC);
