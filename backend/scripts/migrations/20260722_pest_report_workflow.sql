-- 病虫害监测报告、显式识别台账、三级审核与专家会商闭环。

CREATE TABLE IF NOT EXISTS pest_reports (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    report_code VARCHAR(80) NOT NULL,
    report_title VARCHAR(240) NOT NULL,
    scope_level VARCHAR(20) NOT NULL,
    region_code VARCHAR(50) NOT NULL,
    region_name VARCHAR(100) NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    summary TEXT NOT NULL,
    conclusion TEXT NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'draft',
    revision_number INTEGER NOT NULL DEFAULT 1 CHECK (revision_number > 0),
    assessment_count INTEGER NOT NULL DEFAULT 0 CHECK (assessment_count >= 0),
    alert_count INTEGER NOT NULL DEFAULT 0 CHECK (alert_count >= 0),
    snapshot_at TIMESTAMPTZ NOT NULL,
    file_uri VARCHAR(500),
    original_filename VARCHAR(255),
    file_size_bytes BIGINT CHECK (file_size_bytes > 0),
    checksum_sha256 VARCHAR(64),
    created_by VARCHAR(100) NOT NULL,
    created_by_code VARCHAR(50) NOT NULL,
    created_by_role VARCHAR(40) NOT NULL,
    last_review_comment TEXT,
    approved_by VARCHAR(100),
    approved_by_code VARCHAR(50),
    approved_by_role VARCHAR(40),
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_pest_report_code UNIQUE (project_id, report_code),
    CONSTRAINT ck_pest_report_period CHECK (period_end >= period_start),
    CONSTRAINT ck_pest_report_scope CHECK (
        scope_level IN ('province', 'prefecture', 'county')
    ),
    CONSTRAINT ck_pest_report_status CHECK (
        status IN (
            'draft', 'county_review', 'prefecture_review',
            'province_review', 'returned', 'approved'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_pest_reports_project_status
    ON pest_reports (project_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_pest_reports_region_period
    ON pest_reports (scope_level, region_code, period_start, period_end);

CREATE TABLE IF NOT EXISTS pest_report_items (
    id BIGSERIAL PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES pest_reports(id) ON DELETE CASCADE,
    assessment_id INTEGER NOT NULL REFERENCES pest_assessments(id) ON DELETE RESTRICT,
    assessment_code VARCHAR(80) NOT NULL,
    district_code VARCHAR(50) NOT NULL,
    district_name VARCHAR(100) NOT NULL,
    snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_pest_report_assessment UNIQUE (report_id, assessment_id)
);

CREATE INDEX IF NOT EXISTS idx_pest_report_items_report
    ON pest_report_items (report_id, assessment_code);
CREATE INDEX IF NOT EXISTS idx_pest_report_items_district
    ON pest_report_items (district_code, assessment_code);

CREATE TABLE IF NOT EXISTS expert_consultations (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    report_id INTEGER NOT NULL REFERENCES pest_reports(id) ON DELETE CASCADE,
    consultation_code VARCHAR(80) NOT NULL,
    question TEXT NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'open',
    requested_by VARCHAR(100) NOT NULL,
    requested_by_code VARCHAR(50) NOT NULL,
    requested_by_role VARCHAR(40) NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expert_organization VARCHAR(200),
    expert_title VARCHAR(120),
    response TEXT,
    evidence_uri VARCHAR(500),
    evidence_filename VARCHAR(255),
    evidence_size_bytes BIGINT CHECK (evidence_size_bytes > 0),
    evidence_sha256 VARCHAR(64),
    answered_by VARCHAR(100),
    answered_by_code VARCHAR(50),
    answered_by_role VARCHAR(40),
    answered_at TIMESTAMPTZ,
    CONSTRAINT uq_expert_consultation_code UNIQUE (project_id, consultation_code),
    CONSTRAINT ck_expert_consultation_status CHECK (status IN ('open', 'answered'))
);

CREATE INDEX IF NOT EXISTS idx_expert_consultations_report_status
    ON expert_consultations (report_id, status, requested_at DESC);
