BEGIN;

-- 清理旧初始化脚本写入的无实体、无校验和“业务影像”。处理步骤通过级联删除。
DELETE FROM imagery_assets
WHERE asset_code = 'GF2-PMS1-20260618'
  AND data_status = 'operational'
  AND file_uri IS NULL
  AND checksum_sha256 IS NULL
  AND original_filename IS NULL;

COMMIT;
