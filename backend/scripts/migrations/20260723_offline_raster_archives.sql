-- 新增源栅格离线介质分卷封存、来源快照和不可变操作审计。

CREATE TABLE IF NOT EXISTS offline_archives (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL
        REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    delivery_package_id INTEGER NOT NULL
        REFERENCES delivery_packages(id) ON DELETE RESTRICT,
    archive_code VARCHAR(100) NOT NULL,
    archive_name VARCHAR(200) NOT NULL,
    version INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    volume_capacity_bytes BIGINT NOT NULL,
    volume_count INTEGER NOT NULL,
    source_count INTEGER NOT NULL,
    total_source_bytes BIGINT NOT NULL,
    total_archive_bytes BIGINT NOT NULL,
    source_snapshot_sha256 VARCHAR(64) NOT NULL,
    canonical_manifest JSONB NOT NULL,
    manifest_uri VARCHAR(500) NOT NULL,
    manifest_size_bytes BIGINT NOT NULL,
    manifest_checksum_sha256 VARCHAR(64) NOT NULL,
    delivery_package_code VARCHAR(80) NOT NULL,
    delivery_package_completed_at_snapshot TIMESTAMPTZ NOT NULL,
    delivery_package_size_bytes BIGINT NOT NULL,
    delivery_package_checksum_sha256 VARCHAR(64) NOT NULL,
    generated_by VARCHAR(100) NOT NULL,
    generated_by_code VARCHAR(50) NOT NULL,
    generated_by_role VARCHAR(40) NOT NULL,
    generation_comment TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    superseded_at TIMESTAMPTZ,
    CONSTRAINT uq_offline_archive_code UNIQUE (archive_code),
    CONSTRAINT uq_offline_archive_task_version UNIQUE (task_id, version),
    CONSTRAINT ck_offline_archive_status CHECK (
        status IN ('completed', 'superseded', 'invalid')
    ),
    CONSTRAINT ck_offline_archive_counts CHECK (
        volume_capacity_bytes >= 67108864
        AND volume_count > 0
        AND source_count > 0
        AND total_source_bytes > 0
        AND total_archive_bytes > 0
    ),
    CONSTRAINT ck_offline_archive_evidence CHECK (
        manifest_size_bytes > 0
        AND char_length(source_snapshot_sha256) = 64
        AND char_length(manifest_checksum_sha256) = 64
        AND char_length(delivery_package_checksum_sha256) = 64
    )
);

CREATE INDEX IF NOT EXISTS idx_offline_archives_task_version
    ON offline_archives (task_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_offline_archives_task_status
    ON offline_archives (task_id, status, generated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_offline_archives_current
    ON offline_archives (task_id)
    WHERE status = 'completed';

CREATE TABLE IF NOT EXISTS offline_archive_volumes (
    id SERIAL PRIMARY KEY,
    archive_id INTEGER NOT NULL
        REFERENCES offline_archives(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    filename VARCHAR(200) NOT NULL,
    file_uri VARCHAR(500) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    member_count INTEGER NOT NULL,
    source_size_bytes BIGINT NOT NULL,
    volume_manifest JSONB NOT NULL,
    CONSTRAINT uq_offline_archive_volume_sequence
        UNIQUE (archive_id, sequence),
    CONSTRAINT uq_offline_archive_volume_filename
        UNIQUE (archive_id, filename),
    CONSTRAINT ck_offline_archive_volume_evidence CHECK (
        sequence > 0
        AND member_count > 0
        AND source_size_bytes > 0
        AND file_size_bytes > 0
        AND char_length(checksum_sha256) = 64
    )
);

CREATE INDEX IF NOT EXISTS idx_offline_archive_volumes_archive_sequence
    ON offline_archive_volumes (archive_id, sequence);

CREATE TABLE IF NOT EXISTS offline_archive_sources (
    id SERIAL PRIMARY KEY,
    archive_id INTEGER NOT NULL
        REFERENCES offline_archives(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    volume_sequence INTEGER NOT NULL,
    source_kind VARCHAR(30) NOT NULL,
    source_entity_id INTEGER,
    source_entity_code VARCHAR(100) NOT NULL,
    archive_path VARCHAR(500) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_uri VARCHAR(500) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    media_type VARCHAR(120) NOT NULL,
    source_version VARCHAR(100),
    security_classification VARCHAR(30) NOT NULL,
    source_updated_at TIMESTAMPTZ,
    CONSTRAINT uq_offline_archive_source_sequence
        UNIQUE (archive_id, sequence),
    CONSTRAINT uq_offline_archive_source_path
        UNIQUE (archive_id, archive_path),
    CONSTRAINT ck_offline_archive_source_evidence CHECK (
        sequence > 0
        AND volume_sequence > 0
        AND file_size_bytes > 0
        AND char_length(checksum_sha256) = 64
    )
);

CREATE INDEX IF NOT EXISTS idx_offline_archive_sources_archive_volume
    ON offline_archive_sources (archive_id, volume_sequence, sequence);

CREATE TABLE IF NOT EXISTS offline_archive_events (
    id SERIAL PRIMARY KEY,
    archive_id INTEGER NOT NULL
        REFERENCES offline_archives(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    actor_code VARCHAR(50) NOT NULL,
    actor_role VARCHAR(40) NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_offline_archive_events_archive_time
    ON offline_archive_events (archive_id, created_at DESC);
