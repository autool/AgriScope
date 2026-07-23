import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  createPlotAttributeField,
  getPlotAttributeFields,
  updatePlotAttributeField,
} from '@/api/plotAttributeField'
import type {
  PlotAttributeField,
  PlotAttributeFieldCreatePayload,
  PlotAttributeFieldUpdatePayload,
} from '@/types/plotAttributeField'

export const usePlotAttributeFieldStore = defineStore(
  'plot-attribute-field',
  () => {
    const itemsRef = ref<PlotAttributeField[]>([])
    const schemaDigestRef = ref<string>('')
    const projectCodeRef = ref<string>('')
    const loadingRef = ref<boolean>(false)
    const savingRef = ref<boolean>(false)

    const activeFieldsComputed = computed<PlotAttributeField[]>(() => (
      itemsRef.value
        .filter((item) => item.status === 'active')
        .sort((left, right) => (
          left.display_order - right.display_order
          || left.field_code.localeCompare(right.field_code)
        ))
    ))

    const load = async (
      projectCode: string,
      force: boolean = false,
    ): Promise<void> => {
      if (
        loadingRef.value
        || (!force && projectCodeRef.value === projectCode && itemsRef.value.length)
      ) return
      loadingRef.value = true
      try {
        const result = await getPlotAttributeFields(projectCode, true)
        itemsRef.value = result.items
        schemaDigestRef.value = result.schema_digest
        projectCodeRef.value = result.project_code
      } finally {
        loadingRef.value = false
      }
    }

    const create = async (
      projectCode: string,
      payload: PlotAttributeFieldCreatePayload,
    ): Promise<PlotAttributeField> => {
      savingRef.value = true
      try {
        const result = await createPlotAttributeField(projectCode, payload)
        await load(projectCode, true)
        return result
      } finally {
        savingRef.value = false
      }
    }

    const update = async (
      projectCode: string,
      fieldCode: string,
      payload: PlotAttributeFieldUpdatePayload,
    ): Promise<PlotAttributeField> => {
      savingRef.value = true
      try {
        const result = await updatePlotAttributeField(
          projectCode,
          fieldCode,
          payload,
        )
        await load(projectCode, true)
        return result
      } finally {
        savingRef.value = false
      }
    }

    return {
      itemsRef,
      schemaDigestRef,
      projectCodeRef,
      loadingRef,
      savingRef,
      activeFieldsComputed,
      load,
      create,
      update,
    }
  },
)
