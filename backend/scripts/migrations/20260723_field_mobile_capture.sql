-- 移动外业采集：保存浏览器或终端报告的 GPS 水平定位精度。

ALTER TABLE field_verifications
    ADD COLUMN IF NOT EXISTS location_accuracy_m NUMERIC(10, 2);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_field_verification_location_accuracy'
    ) THEN
        ALTER TABLE field_verifications
            ADD CONSTRAINT ck_field_verification_location_accuracy
            CHECK (
                location_accuracy_m IS NULL
                OR (location_accuracy_m > 0 AND location_accuracy_m <= 10000)
            );
    END IF;
END
$$;
