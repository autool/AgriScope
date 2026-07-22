import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  downloadAreaStatisticsHistoryTemplate,
  exportAreaStatisticsCsv,
  getAreaStatistics,
  importAreaStatisticsHistoryCsv,
} from '@/api/index'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  AreaStatistics,
  AreaStatisticsHistoryImportMetadata,
  AreaStatisticsHistoryImportResult,
} from '@/types/workbench'

export const useStatisticsStore = defineStore('statistics', () => {
  const workbenchStore = useWorkbenchStore()
  const userStore = useUserStore()
  const statisticsRef = ref<AreaStatistics | null>(null)
  const loadingRef = ref<boolean>(false)
  const exportingRef = ref<boolean>(false)
  const importingHistoryRef = ref<boolean>(false)
  const canExportComputed = computed<boolean>(() => (
    userStore.hasCapability('export_statistics')
  ))
  const canImportHistoryComputed = computed<boolean>(() => (
    userStore.hasCapability('import_statistics_history')
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
      statisticsRef.value = await getAreaStatistics(
        workbenchStore.taskCodeComputed,
      )
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

  return {
    statisticsRef,
    loadingRef,
    exportingRef,
    importingHistoryRef,
    canExportComputed,
    canImportHistoryComputed,
    load,
    exportCsv,
    importHistoryCsv,
    downloadHistoryTemplate,
  }
})
