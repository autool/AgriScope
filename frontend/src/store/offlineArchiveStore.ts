import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  downloadOfflineArchiveManifest,
  downloadOfflineArchiveVolume,
  generateOfflineArchive,
  getOfflineArchiveOverview,
} from '@/api/offlineArchive'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  OfflineArchive,
  OfflineArchiveGeneratePayload,
  OfflineArchiveOverview,
  OfflineArchiveVolume,
} from '@/types/offlineArchive'

export const useOfflineArchiveStore = defineStore('offlineArchive', () => {
  const userStore = useUserStore()
  const workbenchStore = useWorkbenchStore()
  const overviewRef = ref<OfflineArchiveOverview | null>(null)
  const loadingRef = ref<boolean>(false)
  const generatingRef = ref<boolean>(false)
  const downloadingKeyRef = ref<string | null>(null)
  const canGenerateComputed = computed<boolean>(() => (
    userStore.hasCapability('generate_delivery')
    && Boolean(overviewRef.value?.can_generate)
  ))
  const canDownloadComputed = computed<boolean>(() => (
    userStore.hasCapability('download_delivery')
  ))

  /**
   * 加载离线封存容量预估和版本历史。
   * Returns:
   *   Promise<void>: 工作台数据加载完成后结束。
   */
  const load = async (): Promise<void> => {
    loadingRef.value = true
    try {
      overviewRef.value = await getOfflineArchiveOverview(
        workbenchStore.taskCodeComputed,
      )
    } finally {
      loadingRef.value = false
    }
  }

  /**
   * 生成新的源栅格离线介质封存版本。
   * Args:
   *   payload: 不含操作人编码的容量、名称和依据。
   * Returns:
   *   Promise<OfflineArchive>: 新生成封存版本。
   */
  const generate = async (
    payload: Omit<OfflineArchiveGeneratePayload, 'operator_code'>,
  ): Promise<OfflineArchive> => {
    const user = userStore.currentUserComputed
    if (!user || !canGenerateComputed.value) {
      throw new Error('当前项目身份或业务状态不允许生成离线封存')
    }
    generatingRef.value = true
    try {
      const result = await generateOfflineArchive(
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
   * 下载顶层规范清单。
   * Args:
   *   archive: 待下载封存版本。
   * Returns:
   *   Promise<{blob: Blob, filename: string}>: JSON 实体和文件名。
   */
  const downloadManifest = async (
    archive: OfflineArchive,
  ): Promise<{ blob: Blob; filename: string }> => {
    const user = userStore.currentUserComputed
    if (!user || !canDownloadComputed.value || !archive.is_current) {
      throw new Error('当前项目身份或封存状态不允许下载规范清单')
    }
    downloadingKeyRef.value = `${archive.archive_code}:manifest`
    try {
      return {
        blob: await downloadOfflineArchiveManifest(
          archive.archive_code,
          user.user_code,
        ),
        filename: `${archive.archive_code}-manifest.json`,
      }
    } finally {
      downloadingKeyRef.value = null
    }
  }

  /**
   * 下载一个通过逐成员复核的 ZIP64 分卷。
   * Args:
   *   archive: 分卷所属封存版本。
   *   volume: 待下载分卷。
   * Returns:
   *   Promise<{blob: Blob, filename: string}>: ZIP64 分卷和文件名。
   */
  const downloadVolume = async (
    archive: OfflineArchive,
    volume: OfflineArchiveVolume,
  ): Promise<{ blob: Blob; filename: string }> => {
    const user = userStore.currentUserComputed
    if (!user || !canDownloadComputed.value || !archive.is_current) {
      throw new Error('当前项目身份或封存状态不允许下载分卷')
    }
    downloadingKeyRef.value = `${archive.archive_code}:${volume.sequence}`
    try {
      return {
        blob: await downloadOfflineArchiveVolume(
          archive.archive_code,
          volume.sequence,
          user.user_code,
        ),
        filename: volume.filename,
      }
    } finally {
      downloadingKeyRef.value = null
    }
  }

  return {
    overviewRef,
    loadingRef,
    generatingRef,
    downloadingKeyRef,
    canGenerateComputed,
    canDownloadComputed,
    load,
    generate,
    downloadManifest,
    downloadVolume,
  }
})
