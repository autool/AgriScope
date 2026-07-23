import request from '@/api/request'
import type { FieldCaptureCreatePayload } from '@/types/fieldCapture'
import type { FieldVerificationItem } from '@/types/workbench'

/**
 * 创建一条移动外业记录并执行服务端 PostGIS 点斑匹配。
 * @param taskCode 作业任务编号。
 * @param payload GPS、定位精度、现场属性和稳定采集人编码。
 * @returns 已完成空间匹配的外业记录。
 */
export const createMobileFieldCapture = (
  taskCode: string,
  payload: FieldCaptureCreatePayload,
) => request.post<FieldVerificationItem>(
  '/v1/field-verifications',
  payload,
  {
    params: { task_code: taskCode },
    timeout: 60_000,
  },
)
