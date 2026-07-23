-- 将内业自检提交结构化绑定到最近一次仍有效的全量质检批次。
-- 历史审核记录保持 NULL；新提交由服务端写入受外键保护的批次编号。

ALTER TABLE review_records
    ADD COLUMN IF NOT EXISTS quality_run_code VARCHAR(80);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_review_records_quality_run_code'
    ) THEN
        ALTER TABLE review_records
            ADD CONSTRAINT fk_review_records_quality_run_code
            FOREIGN KEY (quality_run_code)
            REFERENCES task_quality_runs(run_code)
            ON DELETE RESTRICT;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_review_records_quality_run
    ON review_records (quality_run_code);
