import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  exportPlotAttributeWorkbook,
  getPlotAttributeImportBatches,
  importPlotAttributeWorkbook,
} from '@/api/plotAttributeWorkbook'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  PlotAttributeImportBatch,
  PlotAttributeImportBatchList,
} from '@/types/plotAttributeWorkbook'

export const usePlotAttributeWorkbookStore = defineStore(
  'plotAttributeWorkbook',
  () => {
    const userStore = useUserStore()
    const workbenchStore = useWorkbenchStore()
    const historyRef = ref<PlotAttributeImportBatchList | null>(null)
    const latestResultRef = ref<PlotAttributeImportBatch | null>(null)
    const loadingHistoryRef = ref<boolean>(false)
    const exportingRef = ref<boolean>(false)
    const importingRef = ref<boolean>(false)
    const canExportComputed = computed<boolean>(() => (
      workbenchStore.taskEditableComputed
      && userStore.hasCapability('export_plot_attributes')
    ))
    const canImportComputed = computed<boolean>(() => (
      workbenchStore.taskEditableComputed
      && userStore.hasCapability('import_plot_attributes')
    ))

    /**
     * 加载任务最近的 Excel 属性导入批次。
     * Returns:
     *   Promise<void>: 历史证据加载完成后结束。
     */
    const loadHistory = async (): Promise<void> => {
      loadingHistoryRef.value = true
      try {
        historyRef.value = await getPlotAttributeImportBatches(
          workbenchStore.taskCodeComputed,
        )
      } finally {
        loadingHistoryRef.value = false
      }
    }

    /**
     * 下载任务全部或显式范围的当前属性工作簿。
     * Args:
     *   plotCodes: 空值表示请求任务全部图斑，否则为显式范围。
     * Returns:
     *   Promise<{blob: Blob, filename: string}>: XLSX 实体和建议文件名。
     */
    const exportWorkbook = async (
      plotCodes?: string[],
    ): Promise<{ blob: Blob; filename: string }> => {
      const user = userStore.currentUserComputed
      if (!user || !canExportComputed.value) {
        throw new Error('当前项目身份无权导出地块属性工作簿')
      }
      exportingRef.value = true
      try {
        return {
          blob: await exportPlotAttributeWorkbook(
            workbenchStore.taskCodeComputed,
            {
              operator_code: user.user_code,
              plot_codes: plotCodes,
            },
          ),
          filename: `${workbenchStore.taskCodeComputed}_plot_attributes.xlsx`,
        }
      } finally {
        exportingRef.value = false
      }
    }

    /**
     * 上传并原子导入逐行属性工作簿。
     * Args:
     *   file: 原始 XLSX 文件。
     *   comment: 人工判读和证据说明。
     * Returns:
     *   Promise<PlotAttributeImportBatch>: 导入结果和实体证据。
     */
    const importWorkbook = async (
      file: File,
      comment: string,
    ): Promise<PlotAttributeImportBatch> => {
      const user = userStore.currentUserComputed
      if (!user || !canImportComputed.value) {
        throw new Error('当前项目身份无权导入地块属性工作簿')
      }
      importingRef.value = true
      try {
        const result = await importPlotAttributeWorkbook(
          workbenchStore.taskCodeComputed,
          file,
          user.user_code,
          comment,
        )
        latestResultRef.value = result
        await Promise.all([
          loadHistory(),
          workbenchStore.refreshOverview(),
          workbenchStore.refreshPlots(),
        ])
        if (workbenchStore.selectedPlotCodeComputed) {
          await workbenchStore.loadSelectedPlot(
            workbenchStore.selectedPlotCodeComputed,
          )
        }
        return result
      } finally {
        importingRef.value = false
      }
    }

    return {
      historyRef,
      latestResultRef,
      loadingHistoryRef,
      exportingRef,
      importingRef,
      canExportComputed,
      canImportComputed,
      loadHistory,
      exportWorkbook,
      importWorkbook,
    }
  },
)
