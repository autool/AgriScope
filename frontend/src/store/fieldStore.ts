import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  downloadFieldVerificationXlsxTemplate,
  getFieldVerifications,
  importFieldVerificationCsv,
  importFieldVerificationXlsx,
  rematchFieldVerifications,
  reopenFieldVerification,
  resolveFieldVerification,
} from '@/api/index'
import {
  downloadFieldVerificationArtifact,
  uploadFieldVerificationArtifact,
} from '@/api/fieldEvidence'
import { useLayerStore } from '@/store/layerStore'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  FieldResolutionPayload,
  FieldReopenPayload,
  FieldVerificationBatchImportPayload,
  FieldVerificationBatchImportResult,
  FieldVerificationFileImportMetadata,
  FieldVerificationArtifact,
  FieldVerificationArtifactType,
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
  const uploadingArtifactRef = ref<boolean>(false)
  const downloadingArtifactCodeRef = ref<string | null>(null)
  const resolvingRef = ref<boolean>(false)
  const reopeningRef = ref<boolean>(false)
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
  const canViewEvidenceComputed = computed<boolean>(() => (
    userStore.hasCapability('view_field_evidence')
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
   * 为当前外业记录上传一份受控实体证据。
   * Args:
   *   file: 原始照片、语音或调查表。
   *   artifactType: 证据业务类型。
   *   comment: 证据来源和用途说明。
   * Returns:
   *   Promise<FieldVerificationArtifact>: 已通过服务端校验的证据摘要。
   */
  const uploadArtifact = async (
    file: File,
    artifactType: FieldVerificationArtifactType,
    comment: string,
  ): Promise<FieldVerificationArtifact> => {
    const user = userStore.currentUserComputed
    const record = selectedRecordComputed.value
    if (!record) throw new Error('请先选择外业核查记录')
    if (!user || !canUploadComputed.value) {
      throw new Error('当前项目身份无权上传外业实体证据')
    }
    uploadingArtifactRef.value = true
    try {
      const artifact = await uploadFieldVerificationArtifact(
        record.verification_code,
        {
          file,
          artifact_type: artifactType,
          uploader_code: user.user_code,
          comment,
        },
      )
      await Promise.all([load(), workbenchStore.refreshOverview()])
      return artifact
    } finally {
      uploadingArtifactRef.value = false
    }
  }

  /**
   * 下载当前外业记录的一份实体证据。
   * Args:
   *   artifact: 待下载证据摘要。
   * Returns:
   *   Promise<{blob: Blob, filename: string}>: 原始实体及文件名。
   */
  const downloadArtifact = async (
    artifact: FieldVerificationArtifact,
  ): Promise<{ blob: Blob; filename: string }> => {
    const user = userStore.currentUserComputed
    const record = selectedRecordComputed.value
    if (!record) throw new Error('请先选择外业核查记录')
    if (!user || !canViewEvidenceComputed.value) {
      throw new Error('当前项目身份无权查看外业实体证据')
    }
    downloadingArtifactCodeRef.value = artifact.artifact_code
    try {
      return {
        blob: await downloadFieldVerificationArtifact(
          record.verification_code,
          artifact.artifact_code,
          user.user_code,
        ),
        filename: artifact.original_filename,
      }
    } finally {
      downloadingArtifactCodeRef.value = null
    }
  }

  /**
   * 处置当前外业疑点。
   * Args:
   *   payload: 决策、人工依据和可选折中目标属性。
   * Returns:
   *   Promise<void>: 疑点处置和审计写入完成后结束。
   */
  const resolveSelected = async (
    payload: Omit<FieldResolutionPayload, 'reviewer_code'>,
  ): Promise<void> => {
    if (!selectedRecordComputed.value) return
    const user = userStore.currentUserComputed
    if (!user || !canResolveComputed.value) {
      throw new Error('当前项目身份无权处置外业疑点')
    }
    resolvingRef.value = true
    try {
      await resolveFieldVerification(
        selectedRecordComputed.value.verification_code,
        { ...payload, reviewer_code: user.user_code },
      )
      await Promise.all([load(), workbenchStore.refreshOverview()])
    } finally {
      resolvingRef.value = false
    }
  }

  /**
   * 重新打开当前已处置外业疑点。
   * Args:
   *   comment: 新证据或重开原因。
   * Returns:
   *   Promise<void>: 问题恢复和任务门禁回退完成后结束。
   */
  const reopenSelected = async (comment: string): Promise<void> => {
    const record = selectedRecordComputed.value
    const user = userStore.currentUserComputed
    if (!record) return
    if (!user || !canResolveComputed.value) {
      throw new Error('当前项目身份无权重新打开外业疑点')
    }
    const payload: FieldReopenPayload = {
      operator_code: user.user_code,
      comment,
    }
    reopeningRef.value = true
    try {
      await reopenFieldVerification(record.verification_code, payload)
      await Promise.all([load(), workbenchStore.refreshOverview()])
    } finally {
      reopeningRef.value = false
    }
  }

  return {
    listRef,
    selectedCodeRef,
    loadingRef,
    importingRef,
    uploadingArtifactRef,
    downloadingArtifactCodeRef,
    resolvingRef,
    reopeningRef,
    selectedRecordComputed,
    canRematchComputed,
    canResolveComputed,
    canUploadComputed,
    canViewEvidenceComputed,
    load,
    rematch,
    importCsv,
    importXlsx,
    downloadXlsxTemplate,
    uploadArtifact,
    downloadArtifact,
    resolveSelected,
    reopenSelected,
  }
})
