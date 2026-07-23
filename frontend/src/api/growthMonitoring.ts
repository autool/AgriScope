import request from '@/api/request'
import type {
  GrowthArtifactType,
  GrowthMonitoringCreatePayload,
  GrowthMonitoringOverview,
  GrowthMonitoringRun,
} from '@/types/growthMonitoring'

/** 查询真实 NDVI 来源、历史长势任务和选中异常区。 */
export const getGrowthMonitoringOverview = (
  projectCode: string,
  taskCode: string,
  operatorCode: string,
  selectedRunCode?: string,
) => request.get<GrowthMonitoringOverview>('/v1/growth-monitoring/overview', {
  params: {
    project_code: projectCode,
    task_code: taskCode,
    operator_code: operatorCode,
    selected_run_code: selectedRunCode,
  },
  timeout: 120_000,
})

/** 从两期已校验 band_products 实体生成长势分级成果。 */
export const createGrowthMonitoringRun = (
  payload: GrowthMonitoringCreatePayload,
  projectCode: string,
  taskCode: string,
) => request.post<GrowthMonitoringRun>('/v1/growth-monitoring/runs', payload, {
  params: { project_code: projectCode, task_code: taskCode },
  timeout: 300_000,
})

/** 下载并触发长势监测物理成果重新校验和稳定用户审计。 */
export const downloadGrowthMonitoringArtifact = (
  runCode: string,
  artifact: GrowthArtifactType,
  requesterCode: string,
  projectCode: string,
) => request.get<Blob>(
  `/v1/growth-monitoring/runs/${encodeURIComponent(runCode)}/download`,
  {
    params: {
      artifact,
      requester_code: requesterCode,
      project_code: projectCode,
    },
    responseType: 'blob',
    timeout: 120_000,
  },
)
