import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  downloadDisasterReport,
  generateDisasterReport,
  getDisasterReports,
  getDisasterSummary,
  importDisasterGeoJson,
  updateDisasterPatch,
} from '@/api/index'
import { useLayerStore } from '@/store/layerStore'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  DisasterPatch,
  DisasterReport,
  DisasterReportList,
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
  const reportsRef = ref<DisasterReportList | null>(null)
  const selectedCodeRef = ref<string | null>(null)
  const loadingRef = ref<boolean>(false)
  const importingRef = ref<boolean>(false)
  const generatingReportRef = ref<boolean>(false)
  const downloadingReportCodeRef = ref<string | null>(null)
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
  const canGenerateReportComputed = computed<boolean>(() => (
    userStore.hasCapability('generate_disaster_report')
  ))
  const canDownloadReportComputed = computed<boolean>(() => (
    userStore.hasCapability('download_disaster_report')
  ))
  const currentReportComputed = computed<DisasterReport | null>(() => (
    reportsRef.value?.items.find((item) => item.is_current) || null
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
      const [summary, reports] = await Promise.all([
        getDisasterSummary(workbenchStore.taskCodeComputed),
        getDisasterReports(workbenchStore.taskCodeComputed),
      ])
      summaryRef.value = summary
      reportsRef.value = reports
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

  /**
   * 生成当前任务灾害专题报告。
   * Args:
   *   reportTitle: 报告标题。
   *   comment: 报告生成依据。
   * Returns:
   *   Promise<DisasterReport>: 新报告实体摘要。
   */
  const generateReport = async (
    reportTitle: string,
    comment: string,
  ): Promise<DisasterReport> => {
    const user = userStore.currentUserComputed
    if (!user || !canGenerateReportComputed.value) {
      throw new Error('当前项目身份无权生成灾害专题报告')
    }
    generatingReportRef.value = true
    try {
      const report = await generateDisasterReport(
        {
          operator_code: user.user_code,
          report_title: reportTitle,
          comment,
        },
        workbenchStore.taskCodeComputed,
      )
      await Promise.all([load(), workbenchStore.refreshOverview()])
      return report
    } finally {
      generatingReportRef.value = false
    }
  }

  /**
   * 下载并复核指定灾害专题报告实体。
   * Args:
   *   report: 待下载报告。
   * Returns:
   *   Promise<{blob: Blob, filename: string}>: XLSX 实体及文件名。
   */
  const downloadReport = async (
    report: DisasterReport,
  ): Promise<{ blob: Blob; filename: string }> => {
    const user = userStore.currentUserComputed
    if (!user || !canDownloadReportComputed.value) {
      throw new Error('当前项目身份无权下载灾害专题报告')
    }
    downloadingReportCodeRef.value = report.report_code
    try {
      return {
        blob: await downloadDisasterReport(report.report_code, user.user_code),
        filename: `${report.report_code}.xlsx`,
      }
    } finally {
      downloadingReportCodeRef.value = null
    }
  }

  return {
    summaryRef,
    reportsRef,
    selectedCodeRef,
    loadingRef,
    importingRef,
    generatingReportRef,
    downloadingReportCodeRef,
    selectedPatchComputed,
    canReviewComputed,
    canImportComputed,
    canGenerateReportComputed,
    canDownloadReportComputed,
    currentReportComputed,
    load,
    updateSelected,
    importGeoJson,
    generateReport,
    downloadReport,
  }
})
