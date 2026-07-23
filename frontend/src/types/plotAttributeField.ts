export type PlotAttributeFieldType =
  | 'text'
  | 'number'
  | 'date'
  | 'boolean'
  | 'single_select'

export type PlotAttributeFieldStatus = 'active' | 'inactive'
export type CustomAttributeValue = string | number | boolean | null
export type CustomAttributeValues = Record<string, CustomAttributeValue>

export interface PlotAttributeFieldDefinition {
  field_code: string
  label: string
  field_type: PlotAttributeFieldType
  required: boolean
  options: string[]
  display_order: number
  version: number
}

export interface PlotAttributeField extends PlotAttributeFieldDefinition {
  status: PlotAttributeFieldStatus
  created_by: string
  created_by_code: string
  created_by_role: string
  updated_by: string
  updated_by_code: string
  updated_by_role: string
  created_at: string
  updated_at: string
}

export interface PlotAttributeFieldList {
  project_code: string
  schema_digest: string
  active_count: number
  items: PlotAttributeField[]
}

export interface PlotAttributeFieldCreatePayload {
  field_code: string
  label: string
  field_type: PlotAttributeFieldType
  required: boolean
  options: string[]
  display_order: number
  operator_code: string
}

export interface PlotAttributeFieldUpdatePayload {
  label?: string
  field_type?: PlotAttributeFieldType
  required?: boolean
  options?: string[]
  display_order?: number
  status?: PlotAttributeFieldStatus
  operator_code: string
}
