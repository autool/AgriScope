import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  getDisasterSummary,
  importDisasterGeoJson,
  updateDisasterPatch,
} from '@/api/index'
import { useLayerStore } from '@/store/layerStore'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  DisasterPatch,
  DisasterGeoJsonImportPayload,
  DisasterGeoJsonImportResult,
  DisasterPatchUpdatePayload,
  DisasterSummary,
} from '@/types/workbench'

export const useDisasterStore = defineStore('disaster', () => {
  const workbenchStore = useWorkbenchStore()
  const layerStore = useLayerStore()
  const userStore = useUserStore()
  const summaryRef = ref<DisasterSummary | null>(null)
  const selectedCodeRef = ref<string | null>(null)
  const loadingRef = ref<boolean>(false)
  const importingRef = ref<boolean>(false)
  const selectedPatchComputed = computed<DisasterPatch | null>(() => (
    summaryRef.value?.items.find(
      (item) => item.patch_code === selectedCodeRef.value,
    ) || summaryRef.value?.items[0] || null
  ))
  const canReviewComputed = computed<boolean>(() => (
    userStore.hasCapability('review_disaster')
  ))
  const canImportComputed = computed<boolean>(() => (
    workbenchStore.taskEditableComputed
    && userStore.hasCapability('import_disaster')
  ))

  /**
   * 加载灾害斑块并同步专题图层。
   * Args:
   *   无。
   * Returns:
   *   Promise<void>: 灾害数据加载完成后结束。
   */
  const load = async (): Promise<void> => {
    loadingRef.value = true
    try {
      summaryRef.value = await getDisasterSummary(
        workbenchStore.taskCodeComputed,
      )
      layerStore.setDisasterFeatures(summaryRef.value.feature_collection)
      layerStore.setVisibility('disaster', true)
      if (!summaryRef.value.items.some(
        (item) => item.patch_code === selectedCodeRef.value,
      )) {
        selectedCodeRef.value = summaryRef.value.items[0]?.patch_code || null
      }
    } finally {
      loadingRef.value = false
    }
  }

  /**
   * 保存灾害斑块人工复核结果。
   * Args:
   *   severity: 灾害等级。
   *   status: 复核状态。
   *   comment: 复核说明。
   * Returns:
   *   Promise<void>: 复核结果保存并刷新后结束。
   */
  const updateSelected = async (
    severity: DisasterPatchUpdatePayload['severity'],
    status: DisasterPatchUpdatePayload['status'],
    comment: string,
  ): Promise<void> => {
    if (!selectedPatchComputed.value) return
    const user = userStore.currentUserComputed
    if (!user || !canReviewComputed.value) {
      throw new Error('当前项目身份无权复核灾害斑块')
    }
    await updateDisasterPatch(
      selectedPatchComputed.value.patch_code,
      { severity, status, reviewer_code: user.user_code, comment },
      workbenchStore.taskCodeComputed,
    )
    await Promise.all([load(), workbenchStore.refreshOverview()])
  }

  /**
   * 导入灾害模型 GeoJSON 并刷新专题图层和任务审计。
   * Args:
   *   payload: 不含操作人编码的来源与 FeatureCollection。
   * Returns:
   *   Promise<DisasterGeoJsonImportResult>: 导入批次结果。
   */
  const importGeoJson = async (
    payload: Omit<DisasterGeoJsonImportPayload, 'operator_code'>,
  ): Promise<DisasterGeoJsonImportResult> => {
    const user = userStore.currentUserComputed
    if (!user || !canImportComputed.value) {
      throw new Error('当前项目身份或任务状态不允许导入灾害数据')
    }
    importingRef.value = true
    try {
      const result = await importDisasterGeoJson(
        { ...payload, operator_code: user.user_code },
        workbenchStore.taskCodeComputed,
      )
      await Promise.all([load(), workbenchStore.refreshOverview()])
      return result
    } finally {
      importingRef.value = false
    }
  }

  return {
    summaryRef,
    selectedCodeRef,
    loadingRef,
    importingRef,
    selectedPatchComputed,
    canReviewComputed,
    canImportComputed,
    load,
    updateSelected,
    importGeoJson,
  }
})
