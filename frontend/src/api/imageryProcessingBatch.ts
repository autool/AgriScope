import request from '@/api/request'
import type {
  ImageryProcessingBatchRequest,
  ImageryProcessingBatchResponse,
} from '@/types/imageryProcessingBatch'

/** 原子执行 1–10 景影像的同一内置预处理步骤。 */
export const executeImageryProcessingBatch = (
  payload: ImageryProcessingBatchRequest,
  taskCode: string,
) => request.post<ImageryProcessingBatchResponse>(
  '/v1/imagery-assets/processing-batches/execute',
  payload,
  { params: { task_code: taskCode }, timeout: 30 * 60 * 1000 },
)
