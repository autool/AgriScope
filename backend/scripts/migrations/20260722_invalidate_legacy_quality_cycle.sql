-- 最近一次 OSM 底块快照重载后，旧任务范围产生的自动质检结果不得继续
-- 阻断当前周期。人工审核问题和外业问题不在本迁移处理范围内。
WITH target_task AS (
    SELECT id
    FROM monitoring_tasks
    WHERE task_code = 'RS-2026-045'
), cycle_boundary AS (
    SELECT MAX(record.created_at) AS started_at
    FROM review_records AS record
    JOIN target_task AS task ON task.id = record.task_id
    WHERE record.action = 'plot_source_imported'
), resolved_issues AS (
    UPDATE quality_issues AS issue
    SET status = 'resolved',
        resolved_at = NOW(),
        resolved_by = 'OpenStreetMap 数据导入程序',
        resolved_by_code = 'system_osm_import',
        resolved_by_role = 'system',
        resolution_comment = '底块快照已重载，旧自动质检证据失效'
    FROM target_task AS task, cycle_boundary AS cycle
    WHERE issue.task_id = task.id
      AND issue.source = 'auto'
      AND issue.issue_type = 'quality_rule'
      AND issue.status = 'open'
      AND cycle.started_at IS NOT NULL
      AND issue.created_at < cycle.started_at
    RETURNING issue.id
), removed_checks AS (
    DELETE FROM plot_quality_checks AS check_result
    USING target_task AS task, cycle_boundary AS cycle
    WHERE check_result.task_id = task.id
      AND cycle.started_at IS NOT NULL
      AND check_result.checked_at < cycle.started_at
    RETURNING check_result.id
), cleanup_counts AS (
    SELECT
        (SELECT COUNT(*) FROM removed_checks) AS removed_check_count,
        (SELECT COUNT(*) FROM resolved_issues) AS resolved_issue_count
)
INSERT INTO review_records (
    task_id, review_level, action, reviewer,
    reviewer_code, reviewer_role, comment
)
SELECT
    task.id,
    'quality',
    'quality_evidence_invalidated',
    'OpenStreetMap 数据导入程序',
    'system_osm_import',
    'system',
    FORMAT(
        '底块快照重载后删除 %s 条旧检查结果，关闭 %s 条旧自动质量问题；人工审核和外业问题保持不变',
        counts.removed_check_count,
        counts.resolved_issue_count
    )
FROM target_task AS task
CROSS JOIN cleanup_counts AS counts
WHERE counts.removed_check_count + counts.resolved_issue_count > 0
  AND NOT EXISTS (
      SELECT 1
      FROM review_records AS existing
      CROSS JOIN cycle_boundary AS cycle
      WHERE existing.task_id = task.id
        AND existing.action = 'quality_evidence_invalidated'
        AND existing.created_at >= cycle.started_at
  );
