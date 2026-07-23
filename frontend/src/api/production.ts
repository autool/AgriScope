import request from './request'

import type {
  DatasetAsset,
  DatasetAssetCreatePayload,
  DatasetAssetUploadPayload,
  DatasetAssetVerificationResult,
  ProductionBatch,
  ProductionBatchCreatePayload,
  ProductionBatchStatus,
  ProductionOverview,
  WorkPackage,
  WorkPackageCreatePayload,
  WorkPackageCreateResult,
  WorkPackageUpdatePayload,
} from '@/types/production'

const contextParams = (projectCode: string, taskCode: string) => ({
  project_code: projectCode,
  task_code: taskCode,
})

/** 查询当前项目任务的生产调度和多源数据目录。 */
export const getProductionOverview = (
  projectCode: string,
  taskCode: string,
) => request.get<ProductionOverview>('/v1/production/overview', {
  params: contextParams(projectCode, taskCode),
})

/** 登记多源数据资产及其来源和血缘证据。 */
export const registerDatasetAsset = (
  payload: DatasetAssetCreatePayload,
  projectCode: string,
  taskCode: string,
) => request.post<DatasetAsset>('/v1/production/dataset-assets', payload, {
  params: contextParams(projectCode, taskCode),
})

/** 上传实体并由服务端计算 SHA-256 后登记数据资产。 */
export const uploadDatasetAsset = (
  payload: DatasetAssetUploadPayload,
  file: File,
  projectCode: string,
  taskCode: string,
) => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('metadata_json', JSON.stringify(payload))
  return request.post<DatasetAsset>('/v1/production/dataset-assets/upload', formData, {
    params: contextParams(projectCode, taskCode),
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300_000,
  })
}

/** 为既有待核验资产补传实体并保存核验尝试。 */
export const verifyDatasetAsset = (
  assetCode: string,
  file: File,
  operatorCode: string,
  verificationComment: string,
  projectCode: string,
  taskCode: string,
) => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('operator_code', operatorCode)
  formData.append('verification_comment', verificationComment)
  return request.post<DatasetAssetVerificationResult>(
    `/v1/production/dataset-assets/${assetCode}/verify`,
    formData,
    {
      params: contextParams(projectCode, taskCode),
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300_000,
    },
  )
}

/** 下载前由服务端重新校验受控路径、格式、大小和 SHA-256。 */
export const downloadDatasetAsset = (
  assetCode: string,
  operatorCode: string,
  projectCode: string,
  taskCode: string,
) => request.get<Blob>(`/v1/production/dataset-assets/${assetCode}/download`, {
  params: {
    ...contextParams(projectCode, taskCode),
    operator_code: operatorCode,
  },
  responseType: 'blob',
  timeout: 300_000,
})

/** 创建绑定当前规则版本的生产批次。 */
export const createProductionBatch = (
  payload: ProductionBatchCreatePayload,
  projectCode: string,
  taskCode: string,
) => request.post<ProductionBatch>('/v1/production/batches', payload, {
  params: contextParams(projectCode, taskCode),
})

/** 按真实县区批量创建显式图斑作业包。 */
export const createProductionWorkPackages = (
  batchCode: string,
  payload: WorkPackageCreatePayload,
  projectCode: string,
  taskCode: string,
) => request.post<WorkPackageCreateResult>(
  `/v1/production/batches/${batchCode}/work-packages`,
  payload,
  { params: contextParams(projectCode, taskCode), timeout: 60_000 },
)

/** 按服务端状态机流转生产批次。 */
export const updateProductionBatchStatus = (
  batchCode: string,
  status: ProductionBatchStatus,
  operatorCode: string,
  projectCode: string,
  taskCode: string,
) => request.patch<ProductionBatch>(
  `/v1/production/batches/${batchCode}/status`,
  { status, operator_code: operatorCode },
  { params: contextParams(projectCode, taskCode) },
)

/** 更新作业包负责人、期限和生产状态。 */
export const updateProductionWorkPackage = (
  packageCode: string,
  payload: WorkPackageUpdatePayload,
  projectCode: string,
  taskCode: string,
) => request.patch<WorkPackage>(
  `/v1/production/work-packages/${packageCode}`,
  payload,
  { params: contextParams(projectCode, taskCode) },
)
