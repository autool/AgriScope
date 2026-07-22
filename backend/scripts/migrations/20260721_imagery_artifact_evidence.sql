-- 清理没有实体文件证据的历史“完成”状态，防止影像处理链展示假成功。
-- 后续步骤只能通过产物登记接口写入 artifact_evidence 后完成。

BEGIN;

UPDATE imagery_processing_steps
SET status = 'pending',
    progress = 0,
    output_uri = NULL,
    started_at = NULL,
    completed_at = NULL,
    updated_at = NOW()
WHERE NOT (parameters ? 'artifact_evidence');

UPDATE imagery_assets
SET calibration_status = 'pending',
    correction_status = 'pending'
WHERE NOT EXISTS (
    SELECT 1
    FROM imagery_processing_steps AS step
    WHERE step.asset_id = imagery_assets.id
      AND step.parameters ? 'artifact_evidence'
);

COMMIT;
