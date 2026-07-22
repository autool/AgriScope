import request from '@/api/request'
import type {
  ImageryMosaicCreatePayload,
  ImageryMosaicJob,
  ImageryMosaicOverview,
} from '@/types/imageryMosaic'

export const getImageryMosaicOverview = (
  projectCode: string,
  operatorCode: string,
) => request.get<ImageryMosaicOverview>('/v1/imagery-mosaics/overview', {
  params: {
    project_code: projectCode,
    operator_code: operatorCode,
  },
})

export const createImageryMosaicJob = (
  projectCode: string,
  taskCode: string,
  payload: ImageryMosaicCreatePayload,
) => request.post<ImageryMosaicJob>('/v1/imagery-mosaics/jobs', payload, {
  params: {
    project_code: projectCode,
    task_code: taskCode,
  },
  timeout: 300_000,
})

export const downloadImageryMosaicJob = (
  projectCode: string,
  jobCode: string,
  operatorCode: string,
) => request.get<Blob>(
  `/v1/imagery-mosaics/jobs/${encodeURIComponent(jobCode)}/download`,
  {
    params: {
      project_code: projectCode,
      operator_code: operatorCode,
    },
    responseType: 'blob',
    timeout: 300_000,
  },
)
