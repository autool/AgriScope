-- 多时相变化检测首个可交付闭环。
-- 绑定两期真实影像、规则与任务范围快照，保存候选 GeoJSON 和人工判读历史。

CREATE TABLE IF NOT EXISTS change_detection_runs (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL
        REFERENCES monitoring_projects(id) ON DELETE CASCADE,
    task_id INTEGER NOT NULL
        REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    run_code VARCHAR(80) NOT NULL UNIQUE,
    run_name VARCHAR(200) NOT NULL,
    baseline_asset_id INTEGER NOT NULL
        REFERENCES imagery_assets(id) ON DELETE RESTRICT,
    target_asset_id INTEGER NOT NULL
        REFERENCES imagery_assets(id) ON DELETE RESTRICT,
    rule_config_version INTEGER NOT NULL,
    rule_profile_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    task_plot_count INTEGER NOT NULL,
    task_updated_at_snapshot TIMESTAMPTZ NOT NULL,
    alignment_method VARCHAR(120) NOT NULL,
    alignment_offset_pixels NUMERIC(8, 3) NOT NULL,
    alignment_overlap_ratio NUMERIC(7, 4) NOT NULL,
    alignment_evidence_uri VARCHAR(500) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    created_by VARCHAR(100) NOT NULL,
    created_by_code VARCHAR(50) NOT NULL,
    created_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_change_run_assets CHECK (
        baseline_asset_id != target_asset_id
    ),
    CONSTRAINT ck_change_run_plot_count CHECK (task_plot_count > 0),
    CONSTRAINT ck_change_run_alignment CHECK (
        alignment_offset_pixels >= 0
        AND alignment_overlap_ratio > 0
        AND alignment_overlap_ratio <= 1
    ),
    CONSTRAINT ck_change_run_status CHECK (
        status IN ('active', 'reviewing', 'completed', 'cancelled')
    )
);

CREATE INDEX IF NOT EXISTS idx_change_detection_runs_task_status
    ON change_detection_runs (task_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS change_candidates (
    id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL
        REFERENCES change_detection_runs(id) ON DELETE CASCADE,
    candidate_code VARCHAR(80) NOT NULL,
    source_name VARCHAR(120) NOT NULL,
    source_uri VARCHAR(500) NOT NULL,
    source_version VARCHAR(80) NOT NULL,
    source_feature_id VARCHAR(100) NOT NULL,
    source_checksum_sha256 VARCHAR(64) NOT NULL,
    import_batch_code VARCHAR(100) NOT NULL,
    change_class VARCHAR(60) NOT NULL,
    confidence NUMERIC(6, 5) NOT NULL,
    area_ha NUMERIC(16, 4) NOT NULL,
    evidence_uri VARCHAR(500) NOT NULL,
    geom GEOMETRY(POLYGON, 4326) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    exclusion_reason TEXT,
    review_comment TEXT,
    reviewed_by VARCHAR(100),
    reviewed_by_code VARCHAR(50),
    reviewed_by_role VARCHAR(40),
    reviewed_at TIMESTAMPTZ,
    imported_by VARCHAR(100) NOT NULL,
    imported_by_code VARCHAR(50) NOT NULL,
    imported_by_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_change_candidate_code UNIQUE (run_id, candidate_code),
    CONSTRAINT uq_change_candidate_source UNIQUE (
        run_id, source_name, source_feature_id
    ),
    CONSTRAINT ck_change_candidate_class CHECK (
        change_class IN (
            'unclassified',
            'suspected_construction',
            'farmland_outflow',
            'construction_facility_change',
            'non_farmland_agricultural_change',
            'unused_land_change',
            'farmland_attribute_change'
        )
    ),
    CONSTRAINT ck_change_candidate_confidence CHECK (
        confidence >= 0 AND confidence <= 1
    ),
    CONSTRAINT ck_change_candidate_area CHECK (area_ha > 0),
    CONSTRAINT ck_change_candidate_status CHECK (
        status IN ('pending', 'confirmed', 'excluded')
    ),
    CONSTRAINT ck_change_candidate_exclusion CHECK (
        status != 'excluded' OR exclusion_reason IS NOT NULL
    )
);

ALTER TABLE change_candidates
    DROP CONSTRAINT IF EXISTS ck_change_candidate_class;
ALTER TABLE change_candidates
    ADD CONSTRAINT ck_change_candidate_class CHECK (
        change_class IN (
            'unclassified',
            'suspected_construction',
            'farmland_outflow',
            'construction_facility_change',
            'non_farmland_agricultural_change',
            'unused_land_change',
            'farmland_attribute_change'
        )
    );

ALTER TABLE change_candidates
    DROP CONSTRAINT IF EXISTS change_candidates_candidate_code_key;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'change_candidates'::regclass
          AND conname = 'uq_change_candidate_code'
    ) THEN
        ALTER TABLE change_candidates
            ADD CONSTRAINT uq_change_candidate_code
            UNIQUE (run_id, candidate_code);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_change_candidates_run_status
    ON change_candidates (run_id, status, change_class);
CREATE INDEX IF NOT EXISTS idx_change_candidates_import_batch
    ON change_candidates (run_id, import_batch_code);
CREATE INDEX IF NOT EXISTS idx_change_candidates_geom
    ON change_candidates USING GIST (geom);

CREATE TABLE IF NOT EXISTS change_detection_events (
    id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL
        REFERENCES change_detection_runs(id) ON DELETE CASCADE,
    candidate_id INTEGER
        REFERENCES change_candidates(id) ON DELETE CASCADE,
    event_type VARCHAR(40) NOT NULL,
    previous_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    new_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    comment TEXT NOT NULL,
    operator VARCHAR(100) NOT NULL,
    operator_code VARCHAR(50) NOT NULL,
    operator_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_change_detection_events_run_time
    ON change_detection_events (run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_change_detection_events_candidate_time
    ON change_detection_events (candidate_id, created_at DESC)
    WHERE candidate_id IS NOT NULL;
