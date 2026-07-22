BEGIN;

ALTER TABLE change_detection_runs
    ADD COLUMN IF NOT EXISTS registration_job_id INTEGER;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_change_detection_registration_job'
    ) THEN
        ALTER TABLE change_detection_runs
            ADD CONSTRAINT fk_change_detection_registration_job
            FOREIGN KEY (registration_job_id)
            REFERENCES imagery_registration_jobs(id)
            ON DELETE RESTRICT;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_change_detection_registration_job
    ON change_detection_runs (registration_job_id)
    WHERE registration_job_id IS NOT NULL;

COMMIT;
