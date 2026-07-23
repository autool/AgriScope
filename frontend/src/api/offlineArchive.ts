import request from '@/api/request'
import type {
  OfflineArchive,
  OfflineArchiveGeneratePayload,
  OfflineArchiveOverview,
} from '@/types/offlineArchive'

/**
 * 查询真实源栅格容量、生成门禁和离线封存历史。
 * @param taskCode 作业任务编号。
 * @returns 当前容量预估和版本列表。
 */
export const getOfflineArchiveOverview = (
  taskCode: string,
): Promise<OfflineArchiveOverview> => request.get('/v1/offline-archives', {
  params: { task_code: taskCode },
  timeout: 300_000,
})

/**
 * 在服务端生成可独立提取的 ZIP64 分卷。
 * @param payload 容量、名称、操作人和生成依据。
 * @param taskCode 作业任务编号。
 * @returns 新生成的离线封存版本。
 */
export const generateOfflineArchive = (
  payload: OfflineArchiveGeneratePayload,
  taskCode: string,
): Promise<OfflineArchive> => request.post(
  '/v1/offline-archives/generate',
  payload,
  { params: { task_code: taskCode }, timeout: 30 * 60 * 1000 },
)

/**
 * 下载重新校验的顶层规范清单。
 * @param archiveCode 离线封存编号。
 * @param requesterCode 下载人稳定编码。
 * @returns 规范 JSON 实体。
 */
export const downloadOfflineArchiveManifest = (
  archiveCode: string,
  requesterCode: string,
): Promise<Blob> => request.get(
  `/v1/offline-archives/${encodeURIComponent(archiveCode)}/manifest`,
  {
    params: { requester_code: requesterCode },
    responseType: 'blob',
    timeout: 300_000,
  },
)

/**
 * 下载通过逐成员 SHA-256 复核的单个 ZIP64 分卷。
 * @param archiveCode 离线封存编号。
 * @param sequence 分卷序号。
 * @param requesterCode 下载人稳定编码。
 * @returns 可独立提取的 ZIP64 分卷。
 */
export const downloadOfflineArchiveVolume = (
  archiveCode: string,
  sequence: number,
  requesterCode: string,
): Promise<Blob> => request.get(
  `/v1/offline-archives/${encodeURIComponent(archiveCode)}/volumes/${sequence}/download`,
  {
    params: { requester_code: requesterCode },
    responseType: 'blob',
    timeout: 30 * 60 * 1000,
  },
)
