import request from '@/api/request'
import type { ImageryHistoryOverview } from '@/types/imageryHistory'

/** 查询真实县区覆盖矩阵与影像处理证据时间线。 */
export const getImageryHistoryOverview = (
  projectCode: string,
) => request.get<ImageryHistoryOverview>(
  '/v1/imagery-history/overview',
  { params: { project_code: projectCode }, timeout: 120_000 },
)
