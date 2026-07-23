import request from './request'

import type {
  ChangeCandidate,
  ChangeCandidateDiscoveryPayload,
  ChangeCandidateDiscoveryResult,
  ChangeCandidateImportPayload,
  ChangeCandidateImportResult,
  ChangeCandidateReviewPayload,
  ChangeComparisonMetadata,
  ChangeDetectionOverview,
  ChangeDetectionRun,
  ChangeRunCreatePayload,
} from '@/types/changeDetection'

const contextParams = (projectCode: string, taskCode: string) => ({
  project_code: projectCode,
  task_code: taskCode,
})

/** 查询真实影像资格、检测任务、候选队列和判读历史。 */
export const getChangeDetectionOverview = (
  projectCode: string,
  taskCode: string,
) => request.get<ChangeDetectionOverview>('/v1/change-detection/overview', {
  params: contextParams(projectCode, taskCode),
})

/** 创建绑定两期影像、规则快照与实体配准成果的检测任务。 */
export const createChangeDetectionRun = (
  payload: ChangeRunCreatePayload,
  projectCode: string,
  taskCode: string,
) => request.post<ChangeDetectionRun>('/v1/change-detection/runs', payload, {
  params: contextParams(projectCode, taskCode),
})

/** 原子导入外部模型或生产工具生成的候选 GeoJSON。 */
export const importChangeCandidates = (
  runCode: string,
  payload: ChangeCandidateImportPayload,
  projectCode: string,
  taskCode: string,
) => request.post<ChangeCandidateImportResult>(
  `/v1/change-detection/runs/${runCode}/candidates/import-geojson`,
  payload,
  { params: contextParams(projectCode, taskCode), timeout: 60_000 },
)

/** 运行服务端注册的变化评分算法并生成待人工分类候选。 */
export const discoverChangeCandidates = (
  runCode: string,
  payload: ChangeCandidateDiscoveryPayload,
  projectCode: string,
  taskCode: string,
) => request.post<ChangeCandidateDiscoveryResult>(
  `/v1/change-detection/runs/${runCode}/discover-candidates`,
  payload,
  { params: contextParams(projectCode, taskCode), timeout: 180_000 },
)

/** 人工确认、重分类或排除候选并追加不可变历史。 */
export const reviewChangeCandidate = (
  runCode: string,
  candidateCode: string,
  payload: ChangeCandidateReviewPayload,
  projectCode: string,
  taskCode: string,
) => request.patch<ChangeCandidate>(
  `/v1/change-detection/runs/${runCode}/candidates/${candidateCode}/review`,
  payload,
  { params: contextParams(projectCode, taskCode) },
)

/** 生成或读取两期真实栅格公共交集预览及来源清单。 */
export const getChangeComparisonMetadata = (
  runCode: string,
  projectCode: string,
  taskCode: string,
) => request.get<ChangeComparisonMetadata>(
  `/v1/change-detection/runs/${runCode}/comparison`,
  { params: contextParams(projectCode, taskCode), timeout: 120_000 },
)
