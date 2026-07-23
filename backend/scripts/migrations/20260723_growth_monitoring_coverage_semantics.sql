-- 拆分长势监测空间覆盖率与共同范围有效像元率，修正历史字段歧义。

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'growth_monitoring_runs'
          AND column_name = 'minimum_valid_coverage_ratio'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'growth_monitoring_runs'
          AND column_name = 'minimum_valid_pixel_ratio'
    ) THEN
        ALTER TABLE growth_monitoring_runs
            RENAME COLUMN minimum_valid_coverage_ratio TO minimum_valid_pixel_ratio;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'growth_monitoring_runs'
          AND column_name = 'task_mask_pixel_count'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'growth_monitoring_runs'
          AND column_name = 'common_footprint_mask_pixel_count'
    ) THEN
        ALTER TABLE growth_monitoring_runs
            RENAME COLUMN task_mask_pixel_count TO common_footprint_mask_pixel_count;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'growth_monitoring_runs'
          AND column_name = 'valid_coverage_ratio'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'growth_monitoring_runs'
          AND column_name = 'valid_pixel_ratio'
    ) THEN
        ALTER TABLE growth_monitoring_runs
            RENAME COLUMN valid_coverage_ratio TO valid_pixel_ratio;
    END IF;
END $$;

ALTER TABLE growth_monitoring_runs
    ADD COLUMN IF NOT EXISTS minimum_spatial_coverage_ratio NUMERIC(8, 6),
    ADD COLUMN IF NOT EXISTS task_farmland_area_ha NUMERIC(18, 6),
    ADD COLUMN IF NOT EXISTS common_footprint_farmland_area_ha NUMERIC(18, 6),
    ADD COLUMN IF NOT EXISTS spatial_coverage_ratio NUMERIC(8, 6);

WITH measured AS (
    SELECT
        run.id AS run_id,
        ST_Area(task_scope.geom::geography) / 10000.0 AS task_area_ha,
        ST_Area(covered.geom::geography) / 10000.0 AS covered_area_ha
    FROM growth_monitoring_runs AS run
    JOIN imagery_assets AS baseline ON baseline.id = run.baseline_asset_id
    JOIN imagery_assets AS current ON current.id = run.current_asset_id
    JOIN LATERAL (
        SELECT ST_UnaryUnion(ST_Collect(plot.geom)) AS geom
        FROM task_plots AS assignment
        JOIN farmland_plots AS plot ON plot.plot_code = assignment.plot_code
        WHERE assignment.task_id = run.task_id
          AND plot.interpretation_status <> 'deleted'
          AND plot.land_class = '耕地'
    ) AS task_scope ON TRUE
    JOIN LATERAL (
        SELECT ST_Multi(
            ST_CollectionExtract(
                ST_MakeValid(
                    ST_Intersection(
                        task_scope.geom,
                        ST_Intersection(
                            baseline.spatial_extent,
                            current.spatial_extent
                        )
                    )
                ),
                3
            )
        ) AS geom
    ) AS covered ON TRUE
    WHERE task_scope.geom IS NOT NULL
      AND baseline.spatial_extent IS NOT NULL
      AND current.spatial_extent IS NOT NULL
      AND NOT ST_IsEmpty(covered.geom)
), ratios AS (
    SELECT
        run_id,
        task_area_ha,
        covered_area_ha,
        covered_area_ha / NULLIF(task_area_ha, 0) AS coverage_ratio
    FROM measured
    WHERE task_area_ha > 0 AND covered_area_ha > 0
)
UPDATE growth_monitoring_runs AS run
SET
    task_farmland_area_ha = ratios.task_area_ha,
    common_footprint_farmland_area_ha = ratios.covered_area_ha,
    spatial_coverage_ratio = ratios.coverage_ratio,
    minimum_spatial_coverage_ratio = LEAST(ratios.coverage_ratio, 1.0)
FROM ratios
WHERE ratios.run_id = run.id
  AND (
      run.task_farmland_area_ha IS NULL
      OR run.common_footprint_farmland_area_ha IS NULL
      OR run.spatial_coverage_ratio IS NULL
      OR run.minimum_spatial_coverage_ratio IS NULL
  );

ALTER TABLE growth_monitoring_runs
    ALTER COLUMN minimum_spatial_coverage_ratio SET NOT NULL,
    ALTER COLUMN task_farmland_area_ha SET NOT NULL,
    ALTER COLUMN common_footprint_farmland_area_ha SET NOT NULL,
    ALTER COLUMN spatial_coverage_ratio SET NOT NULL;

ALTER TABLE growth_monitoring_runs
    DROP CONSTRAINT IF EXISTS ck_growth_monitoring_thresholds,
    DROP CONSTRAINT IF EXISTS ck_growth_monitoring_counts;

ALTER TABLE growth_monitoring_runs
    ADD CONSTRAINT ck_growth_monitoring_thresholds CHECK (
        poor_delta_threshold >= -1 AND poor_delta_threshold < 0
        AND good_delta_threshold > 0 AND good_delta_threshold <= 1
        AND minimum_zone_area_ha > 0
        AND minimum_spatial_coverage_ratio > 0
        AND minimum_spatial_coverage_ratio <= 1
        AND minimum_valid_pixel_ratio > 0
        AND minimum_valid_pixel_ratio <= 1
    ),
    ADD CONSTRAINT ck_growth_monitoring_counts CHECK (
        task_plot_count > 0
        AND raster_width > 0 AND raster_height > 0
        AND task_farmland_area_ha > 0
        AND common_footprint_farmland_area_ha > 0
        AND common_footprint_farmland_area_ha <= task_farmland_area_ha
        AND spatial_coverage_ratio > 0 AND spatial_coverage_ratio <= 1
        AND common_footprint_mask_pixel_count > 0
        AND valid_pixel_count > 0
        AND valid_pixel_count <= common_footprint_mask_pixel_count
        AND valid_pixel_ratio > 0 AND valid_pixel_ratio <= 1
        AND poor_pixel_count >= 0
        AND normal_pixel_count >= 0
        AND good_pixel_count >= 0
        AND poor_pixel_count + normal_pixel_count + good_pixel_count = valid_pixel_count
        AND anomaly_zone_count >= 0 AND anomaly_area_ha >= 0
    );
