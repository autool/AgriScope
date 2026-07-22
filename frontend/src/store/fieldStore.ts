import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  downloadFieldVerificationXlsxTemplate,
  getFieldVerifications,
  importFieldVerificationCsv,
  importFieldVerificationXlsx,
  rematchFieldVerifications,
  resolveFieldVerification,
} from '@/api/index'
import { useLayerStore } from '@/store/layerStore'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  FieldResolutionPayload,
  FieldVerificationBatchImportPayload,
  FieldVerificationBatchImportResult,
  FieldVerificationFileImportMetadata,
  FieldVerificationItem,
  FieldVerificationList,
} from '@/types/workbench'

export const useFieldStore = defineStore('field', () => {
  const workbenchStore = useWorkbenchStore()
  const layerStore = useLayerStore()
  const userStore = useUserStore()
  const listRef = ref<FieldVerificationList | null>(null)
  const selectedCodeRef = ref<string | null>(null)
  const loadingRef = ref<boolean>(false)
  const importingRef = ref<boolean>(false)
  const selectedRecordComputed = computed<FieldVerificationItem | null>(() => (
    listRef.value?.items.find(
      (item) => item.verification_code === selectedCodeRef.value,
    ) || listRef.value?.items[0] || null
  ))
  const canRematchComputed = computed<boolean>(() => (
    userStore.hasCapability('rematch_field_data')
  ))
  const canResolveComputed = computed<boolean>(() => (
    userStore.hasCapability('resolve_field_issue')
  ))
  const canUploadComputed = computed<boolean>(() => (
    userStore.hasCapability('upload_field_data')
  ))

  const syncLayer = (data: FieldVerificationList): void => {
    listRef.value = data
    layerStore.setFieldFeatures({
      type: 'FeatureCollection',
      features: data.items.map((item) => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [item.lon, item.lat] },
        properties: item,
      })),
    })
  }

  /**
   * 加载外业核查记录和地图点位。
   * Args:
   *   无。
   * Returns:
   *   Promise<void>: 外业记录加载完成后结束。
   */
  const load = async (): Promise<void> => {
    loadingRef.value = true
    try {
      syncLayer(await getFieldVerifications(workbenchStore.taskCodeComputed))
      if (!listRef.value?.items.some(
        (item) => item.verification_code === selectedCodeRef.value,
      )) {
        selectedCodeRef.value = listRef.value?.items[0]?.verification_code || null
      }
    } finally {
      loadingRef.value = false
    }
  }

  /**
   * 重新执行外业点斑空间匹配。
   * Args:
   *   无。
   * Returns:
   *   Promise<void>: 匹配和列表刷新完成后结束。
   */
  const rematch = async (): Promise<void> => {
    const user = userStore.currentUserComputed
    if (!user || !canRematchComputed.value) {
      throw new Error('当前项目身份无权重新匹配外业数据')
    }
    await rematchFieldVerifications(
      { operator_code: user.user_code },
      workbenchStore.taskCodeComputed,
    )
    await load()
  }

  /**
   * 批量导入外业 CSV 记录并刷新点位图层。
   * Args:
   *   payload: 不含上传人编码的来源和记录。
   * Returns:
   *   Promise<FieldVerificationBatchImportResult>: 导入与匹配统计。
   */
  const importCsv = async (
    payload: Omit<FieldVerificationBatchImportPayload, 'uploader_code'>,
  ): Promise<FieldVerificationBatchImportResult> => {
    const user = userStore.currentUserComputed
    if (!user || !canUploadComputed.value) {
      throw new Error('当前项目身份无权导入外业核查数据')
    }
    importingRef.value = true
    try {
      const result = await importFieldVerificationCsv(
        { ...payload, uploader_code: user.user_code },
        workbenchStore.taskCodeComputed,
      )
      await Promise.all([load(), workbenchStore.refreshOverview()])
      return result
    } finally {
      importingRef.value = false
    }
  }

  /**
   * 上传外业 XLSX 实体文件并刷新点位图层。
   * Args:
   *   file: 原始 Excel 工作簿。
   *   metadata: 不含上传人编码的来源和审计说明。
   * Returns:
   *   Promise<FieldVerificationBatchImportResult>: 导入与匹配统计。
   */
  const importXlsx = async (
    file: File,
    metadata: Omit<FieldVerificationFileImportMetadata, 'uploader_code'>,
  ): Promise<FieldVerificationBatchImportResult> => {
    const user = userStore.currentUserComputed
    if (!user || !canUploadComputed.value) {
      throw new Error('当前项目身份无权导入外业核查数据')
    }
    importingRef.value = true
    try {
      const result = await importFieldVerificationXlsx(
        file,
        { ...metadata, uploader_code: user.user_code },
        workbenchStore.taskCodeComputed,
      )
      await Promise.all([load(), workbenchStore.refreshOverview()])
      return result
    } finally {
      importingRef.value = false
    }
  }

  /**
   * 获取服务端生成的外业 XLSX 标准模板。
   * Returns:
   *   Promise<{blob: Blob, filename: string}>: 模板内容和下载文件名。
   */
  const downloadXlsxTemplate = async (): Promise<{
    blob: Blob
    filename: string
  }> => ({
    blob: await downloadFieldVerificationXlsxTemplate(),
    filename: 'field_verification_import_template.xlsx',
  })

  /**
   * 处置当前外业疑点。
   * Args:
   *   decision: 处置决策。
   * Returns:
   *   Promise<void>: 疑点处置和审计写入完成后结束。
   */
  const resolveSelected = async (
    decision: FieldResolutionPayload['decision'],
  ): Promise<void> => {
    if (!selectedRecordComputed.value) return
    const user = userStore.currentUserComputed
    if (!user || !canResolveComputed.value) {
      throw new Error('当前项目身份无权处置外业疑点')
    }
    await resolveFieldVerification(
      selectedRecordComputed.value.verification_code,
      {
        decision,
        reviewer_code: user.user_code,
        comment: decision === 'use_field'
          ? '采用外业调查结论修正内业成果'
          : '复核影像后保留内业成果',
      },
    )
    await Promise.all([load(), workbenchStore.refreshOverview()])
  }

  return {
    listRef,
    selectedCodeRef,
    loadingRef,
    importingRef,
    selectedRecordComputed,
    canRematchComputed,
    canResolveComputed,
    canUploadComputed,
    load,
    rematch,
    importCsv,
    importXlsx,
    downloadXlsxTemplate,
    resolveSelected,
  }
})
