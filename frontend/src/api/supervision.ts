import request from './request'

import type {
  SupervisionCountyEvaluationPayload,
  SupervisionFindingCreatePayload,
  SupervisionInspectionCreatePayload,
  SupervisionOverview,
  SupervisionPlan,
  SupervisionPlanCreatePayload,
  SupervisionRectificationPayload,
  SupervisionReinspectionPayload,
  SupervisionReport,
  SupervisionReportGeneratePayload,
  SupervisionSamplePage,
} from '@/types/supervision'

const contextParams = (projectCode: string, taskCode: string) => ({
  project_code: projectCode,
  task_code: taskCode,
})

/** 查询独立监理工作区、计划和闭环证据。 */
export const getSupervisionOverview = (
  projectCode: string,
  taskCode: string,
) => request.get<SupervisionOverview>('/v1/supervision/overview', {
  params: contextParams(projectCode, taskCode),
})

/** 从任务真实图斑创建县区抽样计划。 */
export const createSupervisionPlan = (
  payload: SupervisionPlanCreatePayload,
  projectCode: string,
  taskCode: string,
) => request.post<SupervisionPlan>('/v1/supervision/plans', payload, {
  params: contextParams(projectCode, taskCode),
  timeout: 60_000,
})

/** 分页读取计划显式抽样图斑。 */
export const getSupervisionSamples = (
  planCode: string,
  page: number,
  pageSize: number,
  regionCode: string | null,
  projectCode: string,
  taskCode: string,
) => request.get<SupervisionSamplePage>(
  `/v1/supervision/plans/${planCode}/samples`,
  {
    params: {
      ...contextParams(projectCode, taskCode),
      page,
      page_size: pageSize,
      region_code: regionCode || undefined,
    },
  },
)

/** 登记独立监理过程检查。 */
export const createSupervisionInspection = (
  planCode: string,
  payload: SupervisionInspectionCreatePayload,
  projectCode: string,
  taskCode: string,
) => request.post<SupervisionPlan>(
  `/v1/supervision/plans/${planCode}/inspections`,
  payload,
  { params: contextParams(projectCode, taskCode) },
)

/** 为过程检查登记监理问题。 */
export const createSupervisionFinding = (
  planCode: string,
  inspectionCode: string,
  payload: SupervisionFindingCreatePayload,
  projectCode: string,
  taskCode: string,
) => request.post<SupervisionPlan>(
  `/v1/supervision/plans/${planCode}/inspections/${inspectionCode}/findings`,
  payload,
  { params: contextParams(projectCode, taskCode) },
)

/** 生产团队提交监理问题整改证据。 */
export const submitSupervisionRectification = (
  planCode: string,
  findingCode: string,
  payload: SupervisionRectificationPayload,
  projectCode: string,
  taskCode: string,
) => request.post<SupervisionPlan>(
  `/v1/supervision/plans/${planCode}/findings/${findingCode}/rectification`,
  payload,
  { params: contextParams(projectCode, taskCode) },
)

/** 独立监理执行逐轮复检。 */
export const reinspectSupervisionFinding = (
  planCode: string,
  findingCode: string,
  payload: SupervisionReinspectionPayload,
  projectCode: string,
  taskCode: string,
) => request.post<SupervisionPlan>(
  `/v1/supervision/plans/${planCode}/findings/${findingCode}/reinspect`,
  payload,
  { params: contextParams(projectCode, taskCode) },
)

/** 新增或更新县区监理量化评价。 */
export const evaluateSupervisionCounty = (
  planCode: string,
  regionCode: string,
  payload: SupervisionCountyEvaluationPayload,
  projectCode: string,
  taskCode: string,
) => request.patch<SupervisionPlan>(
  `/v1/supervision/plans/${planCode}/county-evaluations/${regionCode}`,
  payload,
  { params: contextParams(projectCode, taskCode) },
)

/** 通过闭环门禁后生成不可变监理报告。 */
export const generateSupervisionReport = (
  planCode: string,
  payload: SupervisionReportGeneratePayload,
  projectCode: string,
  taskCode: string,
) => request.post<SupervisionReport>(
  `/v1/supervision/plans/${planCode}/report`,
  payload,
  { params: contextParams(projectCode, taskCode) },
)
