import request from '@/api/request'
import type {
  PlotAttributeField,
  PlotAttributeFieldCreatePayload,
  PlotAttributeFieldList,
  PlotAttributeFieldUpdatePayload,
} from '@/types/plotAttributeField'

export const getPlotAttributeFields = (
  projectCode: string,
  includeInactive: boolean = true,
) => request.get<PlotAttributeFieldList>('/v1/plot-attribute-fields', {
  params: {
    project_code: projectCode,
    include_inactive: includeInactive,
  },
})

export const createPlotAttributeField = (
  projectCode: string,
  payload: PlotAttributeFieldCreatePayload,
) => request.post<PlotAttributeField>('/v1/plot-attribute-fields', payload, {
  params: { project_code: projectCode },
})

export const updatePlotAttributeField = (
  projectCode: string,
  fieldCode: string,
  payload: PlotAttributeFieldUpdatePayload,
) => request.patch<PlotAttributeField>(
  `/v1/plot-attribute-fields/${fieldCode}`,
  payload,
  { params: { project_code: projectCode } },
)
