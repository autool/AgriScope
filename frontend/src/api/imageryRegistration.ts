import request from '@/api/request'
import type {
  ImageryRegistrationCreatePayload,
  ImageryRegistrationJob,
  ImageryRegistrationOverview,
} from '@/types/imageryRegistration'

export const getImageryRegistrationOverview = (
  projectCode: string,
  operatorCode: string,
) => request.get<ImageryRegistrationOverview>(
  '/v1/imagery-registrations/overview',
  {
    params: {
      project_code: projectCode,
      operator_code: operatorCode,
    },
  },
)

export const createImageryRegistrationJob = (
  projectCode: string,
  taskCode: string,
  payload: ImageryRegistrationCreatePayload,
) => request.post<ImageryRegistrationJob>(
  '/v1/imagery-registrations/jobs',
  payload,
  {
    params: {
      project_code: projectCode,
      task_code: taskCode,
    },
    timeout: 300_000,
  },
)

export const downloadImageryRegistrationJob = (
  projectCode: string,
  jobCode: string,
  operatorCode: string,
) => request.get<Blob>(
  `/v1/imagery-registrations/jobs/${encodeURIComponent(jobCode)}/download`,
  {
    params: {
      project_code: projectCode,
      operator_code: operatorCode,
    },
    responseType: 'blob',
    timeout: 300_000,
  },
)
