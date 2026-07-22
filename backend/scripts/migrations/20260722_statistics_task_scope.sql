BEGIN;

-- 删除旧初始化脚本生成的固定年度面积数值，避免与任务真实图斑统计混用。
DELETE FROM area_statistics_snapshots AS snapshot
USING monitoring_projects AS project
WHERE snapshot.project_id = project.id
  AND project.project_code = 'RS-2026'
  AND (
      (snapshot.monitor_year = 2024
       AND snapshot.total_area_ha = 48.7000
       AND snapshot.farmland_area_ha = 42.6000
       AND snapshot.crop_area_ha = 42.6000)
      OR
      (snapshot.monitor_year = 2025
       AND snapshot.total_area_ha = 50.9000
       AND snapshot.farmland_area_ha = 44.2000
       AND snapshot.crop_area_ha = 44.2000)
      OR
      (snapshot.monitor_year = 2026
       AND snapshot.total_area_ha = 52.6000
       AND snapshot.farmland_area_ha = 45.9000
       AND snapshot.crop_area_ha = 45.9000)
  );

COMMIT;
