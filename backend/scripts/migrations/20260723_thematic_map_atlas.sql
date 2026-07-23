-- 新增任务级专题图集编排、成员快照和实体完整性证据。

CREATE TABLE IF NOT EXISTS thematic_map_atlases (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL
        REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
    atlas_code VARCHAR(100) NOT NULL,
    atlas_name VARCHAR(200) NOT NULL,
    atlas_number VARCHAR(100) NOT NULL,
    version INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    package_uri VARCHAR(500) NOT NULL,
    package_size_bytes INTEGER NOT NULL,
    package_checksum_sha256 VARCHAR(64) NOT NULL,
    pdf_filename VARCHAR(200) NOT NULL,
    pdf_size_bytes INTEGER NOT NULL,
    pdf_checksum_sha256 VARCHAR(64) NOT NULL,
    pdf_page_count INTEGER NOT NULL,
    member_count INTEGER NOT NULL,
    product_count_snapshot INTEGER NOT NULL,
    product_latest_at_snapshot TIMESTAMPTZ NOT NULL,
    source_snapshot_sha256 VARCHAR(64) NOT NULL,
    atlas_manifest JSONB NOT NULL,
    generated_by VARCHAR(100) NOT NULL,
    generated_by_code VARCHAR(50) NOT NULL,
    generated_by_role VARCHAR(40) NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    superseded_at TIMESTAMPTZ,
    CONSTRAINT uq_thematic_map_atlas_code UNIQUE (atlas_code),
    CONSTRAINT uq_thematic_map_atlas_task_version UNIQUE (task_id, version),
    CONSTRAINT ck_thematic_map_atlas_status CHECK (
        status IN ('completed', 'superseded', 'invalid')
    ),
    CONSTRAINT ck_thematic_map_atlas_counts CHECK (
        member_count BETWEEN 2 AND 50
        AND pdf_page_count >= member_count + 2
    ),
    CONSTRAINT ck_thematic_map_atlas_file_evidence CHECK (
        package_size_bytes > 0
        AND pdf_size_bytes > 0
        AND char_length(package_checksum_sha256) = 64
        AND char_length(pdf_checksum_sha256) = 64
        AND char_length(source_snapshot_sha256) = 64
    )
);

CREATE INDEX IF NOT EXISTS idx_thematic_map_atlases_task_version
    ON thematic_map_atlases (task_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_thematic_map_atlases_task_status
    ON thematic_map_atlases (task_id, status, generated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_thematic_map_atlases_current
    ON thematic_map_atlases (task_id)
    WHERE status = 'completed';

CREATE TABLE IF NOT EXISTS thematic_map_atlas_items (
    id SERIAL PRIMARY KEY,
    atlas_id INTEGER NOT NULL
        REFERENCES thematic_map_atlases(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL
        REFERENCES thematic_map_products(id) ON DELETE RESTRICT,
    sequence INTEGER NOT NULL,
    product_code VARCHAR(100) NOT NULL,
    map_name VARCHAR(200) NOT NULL,
    map_number VARCHAR(100) NOT NULL,
    map_date DATE NOT NULL,
    product_size_bytes INTEGER NOT NULL,
    product_checksum_sha256 VARCHAR(64) NOT NULL,
    member_path VARCHAR(300) NOT NULL,
    CONSTRAINT uq_thematic_map_atlas_item_sequence
        UNIQUE (atlas_id, sequence),
    CONSTRAINT uq_thematic_map_atlas_item_product
        UNIQUE (atlas_id, product_id),
    CONSTRAINT ck_thematic_map_atlas_item_evidence CHECK (
        sequence BETWEEN 1 AND 50
        AND product_size_bytes > 0
        AND char_length(product_checksum_sha256) = 64
    )
);

CREATE INDEX IF NOT EXISTS idx_thematic_map_atlas_items_atlas_sequence
    ON thematic_map_atlas_items (atlas_id, sequence);
