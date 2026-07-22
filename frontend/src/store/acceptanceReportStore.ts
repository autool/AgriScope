import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  downloadAcceptanceReport,
  generateAcceptanceReport,
  getAcceptanceReports,
} from '@/api/acceptanceReport'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  AcceptanceReport,
  AcceptanceReportGeneratePayload,
  AcceptanceReportList,
} from '@/types/acceptanceReport'

export const useAcceptanceReportStore = defineStore('acceptanceReport', () => {
  const userStore = useUserStore()
  const workbenchStore = useWorkbenchStore()
  const listRef = ref<AcceptanceReportList | null>(null)
  const loadingRef = ref<boolean>(false)
  const generatingRef = ref<boolean>(false)
  const downloadingCodeRef = ref<string | null>(null)
  const canGenerateComputed = computed<boolean>(() => (
    userStore.hasCapability('generate_acceptance_report')
    && Boolean(listRef.value?.can_generate)
  ))
  const canDownloadComputed = computed<boolean>(() => (
    userStore.hasCapability('download_acceptance_report')
  ))

  /**
   * 加载验收报告门禁和版本列表。
   * Returns:
   *   Promise<void>: 数据加载完成后结束。
   */
  const load = async (): Promise<void> => {
    loadingRef.value = true
    try {
      listRef.value = await getAcceptanceReports(workbenchStore.taskCodeComputed)
    } finally {
      loadingRef.value = false
    }
  }

  /**
   * 生成绑定当前成果包的正式验收报告。
   * Args:
   *   payload: 不含操作人编码的报告标题和依据。
   * Returns:
   *   Promise<AcceptanceReport>: 新报告版本。
   */
  const generate = async (
    payload: Omit<AcceptanceReportGeneratePayload, 'operator_code'>,
  ): Promise<AcceptanceReport> => {
    const user = userStore.currentUserComputed
    if (!user || !canGenerateComputed.value) {
      throw new Error(listRef.value?.generate_blocker || '当前身份无权生成验收报告')
    }
    generatingRef.value = true
    try {
      const report = await generateAcceptanceReport(
        { ...payload, operator_code: user.user_code },
        workbenchStore.taskCodeComputed,
      )
      await Promise.all([load(), workbenchStore.refreshOverview()])
      return report
    } finally {
      generatingRef.value = false
    }
  }

  /**
   * 下载通过 DOCX/PDF 和清单复核的验收报告 ZIP。
   * Args:
   *   report: 待下载报告。
   * Returns:
   *   Promise<{blob: Blob, filename: string}>: ZIP 和文件名。
   */
  const download = async (
    report: AcceptanceReport,
  ): Promise<{ blob: Blob; filename: string }> => {
    const user = userStore.currentUserComputed
    if (!user || !canDownloadComputed.value) {
      throw new Error('当前项目身份无权下载验收报告')
    }
    downloadingCodeRef.value = report.report_code
    try {
      return {
        blob: await downloadAcceptanceReport(
          report.report_code,
          user.user_code,
        ),
        filename: `${report.report_code}.zip`,
      }
    } finally {
      downloadingCodeRef.value = null
    }
  }

  return {
    listRef,
    loadingRef,
    generatingRef,
    downloadingCodeRef,
    canGenerateComputed,
    canDownloadComputed,
    load,
    generate,
    download,
  }
})
