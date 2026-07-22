-- 清理早期固定写入的项目进度。工作台进度现由业务影像、任务图斑、
-- 质量门禁、外业记录、三级审核和当前有效成果包六类证据实时计算。
UPDATE monitoring_projects
SET progress = 0,
    updated_at = NOW()
WHERE project_code = 'RS-2026'
  AND progress = 46.00;
