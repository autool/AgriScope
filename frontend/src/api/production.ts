import request from './request'

import type {
  DatasetAsset,
  DatasetAssetCreatePayload,
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
