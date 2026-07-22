import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  downloadStatisticsReport,
  downloadAreaStatisticsHistoryTemplate,
  exportAreaStatisticsCsv,
  generateStatisticsReport,
  getAreaStatistics,
  getStatisticsReports,
  importAreaStatisticsHistoryCsv,
} from '@/api/index'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  AreaStatistics,
  AreaStatisticsHistoryImportMetadata,
  AreaStatisticsHistoryImportResult,
  StatisticsReport,
  StatisticsReportList,
} from '@/types/workbench'

export const useStatisticsStore = defineStore('statistics', () => {
  const workbenchStore = useWorkbenchStore()
  const userStore = useUserStore()
  const statisticsRef = ref<AreaStatistics | null>(null)
  const reportsRef = ref<StatisticsReportList | null>(null)
  const loadingRef = ref<boolean>(false)
  const exportingRef = ref<boolean>(false)
  const importingHistoryRef = ref<boolean>(false)
  const generatingReportRef = ref<boolean>(false)
  const downloadingReportCodeRef = ref<string | null>(null)
  const canExportComputed = computed<boolean>(() => (
    userStore.hasCapability('export_statistics')
  ))
  const canImportHistoryComputed = computed<boolean>(() => (
    userStore.hasCapability('import_statistics_history')
  ))
  const canGenerateReportComputed = computed<boolean>(() => (
    userStore.hasCapability('generate_statistics_report')
  ))
  const canDownloadReportComputed = computed<boolean>(() => (
    userStore.hasCapability('download_statistics_report')
  ))

  /**
   * 加载 PostGIS 多维面积统计。
   * Args:
   *   无。
   * Returns:
   *   Promise<void>: 面积统计加载完成后结束。
   */
  const load = async (): Promise<void> => {
    loadingRef.value = true
    try {
      const [statistics, reports] = await Promise.all([
        getAreaStatistics(workbenchStore.taskCodeComputed),
        getStatisticsReports(workbenchStore.taskCodeComputed),
      ])
      statisticsRef.value = statistics
      reportsRef.value = reports
    } finally {
      loadingRef.value = false
    }
  }

  /**
   * 下载当前任务多维面积统计 CSV。
   * Args:
   *   无。
   * Returns:
   *   Promise<{blob: Blob, filename: string}>: 下载文件内容和文件名。
   */
  const exportCsv = async (): Promise<{ blob: Blob; filename: string }> => {
    const user = userStore.currentUserComputed
    if (!user || !canExportComputed.value) {
      throw new Error('当前项目身份无权导出统计成果')
    }
    exportingRef.value = true
    try {
      const blob = await exportAreaStatisticsCsv(
        user.user_code,
        workbenchStore.taskCodeComputed,
      )
      const monitorYear = statisticsRef.value?.monitor_year || 'current'
      return {
        blob,
        filename: `${workbenchStore.taskCodeComputed}_area_statistics_${monitorYear}.csv`,
      }
    } finally {
      exportingRef.value = false
    }
  }

  /**
   * 导入真实历史年度统计 CSV 并刷新趋势。
   * Args:
   *   file: 原始 CSV 文件。
   *   metadata: 不含操作人编码的来源和冲突策略。
   * Returns:
   *   Promise<AreaStatisticsHistoryImportResult>: 导入批次和年度结果。
   */
  const importHistoryCsv = async (
    file: File,
    metadata: Omit<AreaStatisticsHistoryImportMetadata, 'operator_code'>,
  ): Promise<AreaStatisticsHistoryImportResult> => {
    const user = userStore.currentUserComputed
    if (!user || !canImportHistoryComputed.value) {
      throw new Error('当前项目身份无权导入历史年度统计')
    }
    importingHistoryRef.value = true
    try {
      const result = await importAreaStatisticsHistoryCsv(
        file,
        { ...metadata, operator_code: user.user_code },
        workbenchStore.taskCodeComputed,
      )
      await Promise.all([load(), workbenchStore.refreshOverview()])
      return result
    } finally {
      importingHistoryRef.value = false
    }
  }

  /**
   * 下载历史年度统计 CSV 标准模板。
   * Returns:
   *   Promise<{blob: Blob, filename: string}>: 模板内容和文件名。
   */
  const downloadHistoryTemplate = async (): Promise<{
    blob: Blob
    filename: string
  }> => ({
    blob: await downloadAreaStatisticsHistoryTemplate(),
    filename: 'area_statistics_history_template.csv',
  })

  /**
   * 生成服务端正式面积统计报告包。
   * Args:
   *   reportTitle: 报告标题。
   *   comment: 生成依据。
   * Returns:
   *   Promise<StatisticsReport>: 新生成报告摘要。
   */
  const generateReport = async (
    reportTitle: string,
    comment: string,
  ): Promise<StatisticsReport> => {
    const user = userStore.currentUserComputed
    if (!user || !canGenerateReportComputed.value) {
      throw new Error('当前项目身份无权生成正式统计报告')
    }
    generatingReportRef.value = true
    try {
      const report = await generateStatisticsReport(
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
   * 下载服务端校验后的正式统计报告 ZIP。
   * Args:
   *   report: 待下载报告摘要。
   * Returns:
   *   Promise<{blob: Blob, filename: string}>: 报告包和文件名。
   */
  const downloadReport = async (
    report: StatisticsReport,
  ): Promise<{ blob: Blob; filename: string }> => {
    const user = userStore.currentUserComputed
    if (!user || !canDownloadReportComputed.value) {
      throw new Error('当前项目身份无权下载正式统计报告')
    }
    downloadingReportCodeRef.value = report.report_code
    try {
      return {
        blob: await downloadStatisticsReport(
          report.report_code,
          user.user_code,
        ),
        filename: `${report.report_code}.zip`,
      }
    } finally {
      downloadingReportCodeRef.value = null
    }
  }

  return {
    statisticsRef,
    reportsRef,
    loadingRef,
    exportingRef,
    importingHistoryRef,
    generatingReportRef,
    downloadingReportCodeRef,
    canExportComputed,
    canImportHistoryComputed,
    canGenerateReportComputed,
    canDownloadReportComputed,
    load,
    exportCsv,
    importHistoryCsv,
    downloadHistoryTemplate,
    generateReport,
    downloadReport,
  }
})
