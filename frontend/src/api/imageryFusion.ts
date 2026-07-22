import request from '@/api/request'
import type {
  ImageryFusionCreatePayload,
  ImageryFusionJob,
  ImageryFusionOverview,
} from '@/types/imageryFusion'

export const getImageryFusionOverview = (
  projectCode: string,
  operatorCode: string,
) => request.get<ImageryFusionOverview>('/v1/imagery-fusions/overview', {
  params: { project_code: projectCode, operator_code: operatorCode },
})

export const createImageryFusionJob = (
  projectCode: string,
  taskCode: string,
  payload: ImageryFusionCreatePayload,
) => request.post<ImageryFusionJob>('/v1/imagery-fusions/jobs', payload, {
  params: { project_code: projectCode, task_code: taskCode },
  timeout: 300_000,
})

export const downloadImageryFusionJob = (
  projectCode: string,
  jobCode: string,
  operatorCode: string,
) => request.get<Blob>(
  `/v1/imagery-fusions/jobs/${encodeURIComponent(jobCode)}/download`,
  {
    params: { project_code: projectCode, operator_code: operatorCode },
    responseType: 'blob',
    timeout: 300_000,
  },
)
