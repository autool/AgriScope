import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  downloadVectorExport,
  generateVectorExport,
  getVectorExportOptions,
  getVectorExports,
} from '@/api/vectorExport'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  VectorExportGeneratePayload,
  VectorExportList,
  VectorExportOptions,
  VectorExportPackage,
} from '@/types/vectorExport'

export const useVectorExportStore = defineStore('vectorExport', () => {
  const userStore = useUserStore()
  const workbenchStore = useWorkbenchStore()
  const listRef = ref<VectorExportList | null>(null)
  const optionsRef = ref<VectorExportOptions | null>(null)
  const loadingRef = ref<boolean>(false)
  const generatingRef = ref<boolean>(false)
  const downloadingCodeRef = ref<string | null>(null)
  const canGenerateComputed = computed<boolean>(() => (
    userStore.hasCapability('generate_vector_export')
  ))
  const canDownloadComputed = computed<boolean>(() => (
    userStore.hasCapability('download_vector_export')
  ))

  /**
   * 加载导出版本和真实筛选范围。
   * Returns:
   *   Promise<void>: 数据加载完成后结束。
   */
  const load = async (): Promise<void> => {
    loadingRef.value = true
    try {
      const [list, options] = await Promise.all([
        getVectorExports(workbenchStore.taskCodeComputed),
        getVectorExportOptions(workbenchStore.taskCodeComputed),
      ])
      listRef.value = list
      optionsRef.value = options
    } finally {
      loadingRef.value = false
    }
  }

  /**
   * 生成受控多格式矢量成果包。
   * Args:
   *   payload: 不含操作人编码的格式、筛选和依据。
   * Returns:
   *   Promise<VectorExportPackage>: 新生成导出版本。
   */
  const generate = async (
    payload: Omit<VectorExportGeneratePayload, 'operator_code'>,
  ): Promise<VectorExportPackage> => {
    const user = userStore.currentUserComputed
    if (!user || !canGenerateComputed.value) {
      throw new Error('当前项目身份无权生成矢量成果')
    }
    generatingRef.value = true
    try {
      const result = await generateVectorExport(
        { ...payload, operator_code: user.user_code },
        workbenchStore.taskCodeComputed,
      )
      await Promise.all([load(), workbenchStore.refreshOverview()])
      return result
    } finally {
      generatingRef.value = false
    }
  }

  /**
   * 下载通过完整格式复核的矢量成果 ZIP。
   * Args:
   *   item: 待下载导出版本。
   * Returns:
   *   Promise<{blob: Blob, filename: string}>: ZIP 和文件名。
   */
  const download = async (
    item: VectorExportPackage,
  ): Promise<{ blob: Blob; filename: string }> => {
    const user = userStore.currentUserComputed
    if (!user || !canDownloadComputed.value) {
      throw new Error('当前项目身份无权下载矢量成果')
    }
    downloadingCodeRef.value = item.export_code
    try {
      return {
        blob: await downloadVectorExport(item.export_code, user.user_code),
        filename: `${item.export_code}.zip`,
      }
    } finally {
      downloadingCodeRef.value = null
    }
  }

  return {
    listRef,
    optionsRef,
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
