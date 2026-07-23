import request from '@/api/request'
import type { ImageryBatchResponse } from '@/types/imageryBatch'

/** 原子上传 1–20 个影像实体和规范化批次清单。 */
export const uploadImageryAssetBatch = (
  formData: FormData,
  projectCode: string,
  taskCode: string,
  onProgress?: (progress: number) => void,
) => request.post<ImageryBatchResponse>('/v1/imagery-assets/batch', formData, {
  params: { project_code: projectCode, task_code: taskCode },
  headers: { 'Content-Type': 'multipart/form-data' },
  timeout: 20 * 60 * 1000,
  onUploadProgress: (event) => {
    if (!onProgress || !event.total) return
    onProgress(Math.round((event.loaded / event.total) * 100))
  },
})
