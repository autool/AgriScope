import request from '@/api/request'
import type {
  AcceptanceReport,
  AcceptanceReportGeneratePayload,
  AcceptanceReportList,
} from '@/types/acceptanceReport'

/**
 * 查询任务成果验收正式报告门禁和版本历史。
 * @param taskCode 作业任务编号。
 * @returns 当前业务门禁和报告版本。
 */
export const getAcceptanceReports = (
  taskCode: string,
): Promise<AcceptanceReportList> => request.get('/v1/acceptance-reports', {
  params: { task_code: taskCode },
  timeout: 60_000,
})

/**
 * 基于当前有效成果包生成 DOCX/PDF 验收报告。
 * @param payload 报告标题、生成依据和稳定用户编码。
 * @param taskCode 作业任务编号。
 * @returns 新生成验收报告。
 */
export const generateAcceptanceReport = (
  payload: AcceptanceReportGeneratePayload,
  taskCode: string,
): Promise<AcceptanceReport> => request.post(
  '/v1/acceptance-reports/generate',
  payload,
  { params: { task_code: taskCode }, timeout: 300_000 },
)

/**
 * 下载服务端重新校验的 DOCX/PDF 验收报告 ZIP。
 * @param reportCode 验收报告编号。
 * @param requesterCode 下载人稳定编码。
 * @returns 报告 ZIP 实体。
 */
export const downloadAcceptanceReport = (
  reportCode: string,
  requesterCode: string,
): Promise<Blob> => request.get(
  `/v1/acceptance-reports/${encodeURIComponent(reportCode)}/download`,
  {
    params: { requester_code: requesterCode },
    responseType: 'blob',
    timeout: 300_000,
  },
)
