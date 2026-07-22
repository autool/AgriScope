import request from './request'

import type {
  ThematicMapBatchGeneratePayload,
  ThematicMapBatchGenerateResult,
  ThematicMapOverview,
  ThematicMapTemplate,
  ThematicMapTemplateCreatePayload,
} from '@/types/thematicMap'

export const getThematicMapOverview = (
  projectCode: string,
  taskCode: string,
) => request.get<ThematicMapOverview>('/v1/thematic-maps/overview', {
  params: { project_code: projectCode, task_code: taskCode },
})

export const createThematicMapTemplate = (
  payload: ThematicMapTemplateCreatePayload,
  projectCode: string,
  taskCode: string,
) => request.post<ThematicMapTemplate>('/v1/thematic-maps/templates', payload, {
  params: { project_code: projectCode, task_code: taskCode },
})

export const generateThematicMapProducts = (
  payload: ThematicMapBatchGeneratePayload,
  projectCode: string,
  taskCode: string,
) => request.post<ThematicMapBatchGenerateResult>(
  '/v1/thematic-maps/products/generate',
  payload,
  {
    params: { project_code: projectCode, task_code: taskCode },
    timeout: 10 * 60 * 1000,
  },
)
