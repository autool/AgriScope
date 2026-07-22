-- 为早期底块导入审计补齐稳定系统身份；不修改人工审核人的历史快照。
UPDATE review_records
SET reviewer_code = 'system_osm_import',
    reviewer_role = 'system'
WHERE action = 'plot_source_imported'
  AND reviewer = 'OpenStreetMap 数据导入程序'
  AND reviewer_code IS NULL;
