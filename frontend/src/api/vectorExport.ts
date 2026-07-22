import request from '@/api/request'
import type {
  VectorExportGeneratePayload,
  VectorExportList,
  VectorExportOptions,
  VectorExportPackage,
} from '@/types/vectorExport'

/**
 * 查询任务多格式矢量成果历史。
 * @param taskCode 作业任务编号。
 * @returns 当前与历史导出版本。
 */
export const getVectorExports = (
  taskCode: string,
): Promise<VectorExportList> => request.get('/v1/vector-exports', {
  params: { task_code: taskCode },
  timeout: 60_000,
})

/**
 * 查询真实县区、地类和格式能力。
 * @param taskCode 作业任务编号。
 * @returns 任务范围筛选项和数量门禁。
 */
export const getVectorExportOptions = (
  taskCode: string,
): Promise<VectorExportOptions> => request.get('/v1/vector-exports/options', {
  params: { task_code: taskCode },
  timeout: 60_000,
})

/**
 * 生成真实 GeoJSON、Shapefile、KML 和 FileGDB 成果包。
 * @param payload 格式、筛选、标题和审计依据。
 * @param taskCode 作业任务编号。
 * @returns 新生成导出包。
 */
export const generateVectorExport = (
  payload: VectorExportGeneratePayload,
  taskCode: string,
): Promise<VectorExportPackage> => request.post(
  '/v1/vector-exports/generate',
  payload,
  { params: { task_code: taskCode }, timeout: 300_000 },
)

/**
 * 下载服务端重新校验的多格式矢量成果 ZIP。
 * @param exportCode 导出包业务编号。
 * @param requesterCode 下载人稳定编码。
 * @returns 实体 ZIP。
 */
export const downloadVectorExport = (
  exportCode: string,
  requesterCode: string,
): Promise<Blob> => request.get(
  `/v1/vector-exports/${encodeURIComponent(exportCode)}/download`,
  {
    params: { requester_code: requesterCode },
    responseType: 'blob',
    timeout: 300_000,
  },
)
