import request from '@/api/request'
import type {
  ImagerySourceAcceptanceBatchRequest,
  ImagerySourceAcceptanceBatchResponse,
} from '@/types/imagerySourceAcceptance'

/** 原子承认 1–10 景 L2A/L2 源产品的辐射定标和大气校正要求。 */
export const acceptImagerySourceLevelBatch = (
  payload: ImagerySourceAcceptanceBatchRequest,
  taskCode: string,
) => request.post<ImagerySourceAcceptanceBatchResponse>(
  '/v1/imagery-assets/source-acceptance-batches',
  payload,
  { params: { task_code: taskCode }, timeout: 10 * 60 * 1000 },
)
