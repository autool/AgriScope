import request from '@/api/request'
import type {
  PlotAttributeImportBatch,
  PlotAttributeImportBatchList,
  PlotAttributeWorkbookExportPayload,
} from '@/types/plotAttributeWorkbook'

/**
 * 导出包含当前版本和逐图斑属性的 XLSX。
 * @param taskCode 作业任务编号。
 * @param payload 操作人和可选显式图斑范围。
 * @returns 可编辑并可回写的 Excel 实体。
 */
export const exportPlotAttributeWorkbook = (
  taskCode: string,
  payload: PlotAttributeWorkbookExportPayload,
): Promise<Blob> => request.post(
  `/v1/plot-attribute-workbooks/tasks/${encodeURIComponent(taskCode)}/export.xlsx`,
  payload,
  { responseType: 'blob', timeout: 60_000 },
)

/**
 * 服务端严格解析并原子导入地块属性 XLSX。
 * @param taskCode 作业任务编号。
 * @param file 原始工作簿实体。
 * @param operatorCode 稳定项目用户编码。
 * @param comment 影像、外业或调查表证据说明。
 * @returns 导入批次和实体校验值。
 */
export const importPlotAttributeWorkbook = (
  taskCode: string,
  file: File,
  operatorCode: string,
  comment: string,
): Promise<PlotAttributeImportBatch> => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('operator_code', operatorCode)
  formData.append('comment', comment)
  return request.post(
    `/v1/plot-attribute-workbooks/tasks/${encodeURIComponent(taskCode)}/import`,
    formData,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120_000,
    },
  )
}

/**
 * 查询任务最近的属性工作簿导入证据。
 * @param taskCode 作业任务编号。
 * @returns 最近 20 个实体导入批次。
 */
export const getPlotAttributeImportBatches = (
  taskCode: string,
): Promise<PlotAttributeImportBatchList> => request.get(
  `/v1/plot-attribute-workbooks/tasks/${encodeURIComponent(taskCode)}/imports`,
)
