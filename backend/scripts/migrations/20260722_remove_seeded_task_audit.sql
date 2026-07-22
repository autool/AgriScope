-- 删除早期初始化脚本写入的固定人员、固定时间伪审核记录。
-- 真实底块导入和后续业务操作审计均保留。
DELETE FROM review_records
WHERE action = 'created'
  AND reviewer = '李静'
  AND reviewer_code = 'interp-li-jing'
  AND comment = '创建地块解译作业单元'
  AND created_at = TIMESTAMPTZ '2026-07-21 09:42:00+08';
