import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { getAdministrativeBoundaries } from '@/api/index'
import {
  createImageryMosaicJob,
  downloadImageryMosaicJob,
  getImageryMosaicOverview,
} from '@/api/imageryMosaic'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  ImageryMosaicBoundaryFeature,
  ImageryMosaicCreatePayload,
  ImageryMosaicOverview,
} from '@/types/imageryMosaic'

export const useImageryMosaicStore = defineStore('imageryMosaic', () => {
  const userStore = useUserStore()
  const workbenchStore = useWorkbenchStore()
  const overviewRef = ref<ImageryMosaicOverview | null>(null)
  const boundariesRef = ref<ImageryMosaicBoundaryFeature[]>([])
  const loadingRef = ref<boolean>(false)
  const creatingRef = ref<boolean>(false)
  const downloadingJobCodeRef = ref<string | null>(null)
  const canProcessComputed = computed<boolean>(() => (
    userStore.hasCapability('process_imagery')
  ))

  const requireUserCode = (): string => {
    const userCode = userStore.currentUserComputed?.user_code
    if (!userCode || !canProcessComputed.value) {
      throw new Error('当前项目身份无权执行多景影像生产')
    }
    return userCode
  }

  /**
   * 加载已校验来源、真实行政区边界和历史实体成果。
   * Args:
   *   无。
   * Returns:
   *   Promise<void>: 镶嵌工作台数据加载完成后结束。
   */
  const load = async (): Promise<void> => {
    loadingRef.value = true
    try {
      await userStore.initialize(workbenchStore.projectCodeComputed)
      const userCode = requireUserCode()
      const [overview, boundaries] = await Promise.all([
        getImageryMosaicOverview(
          workbenchStore.projectCodeComputed,
          userCode,
        ),
        getAdministrativeBoundaries(workbenchStore.projectCodeComputed),
      ])
      overviewRef.value = overview
      boundariesRef.value = boundaries.features
    } finally {
      loadingRef.value = false
    }
  }

  /**
   * 创建并执行一个多景镶嵌任务。
   * Args:
   *   payload: 不含客户端角色的业务参数。
   * Returns:
   *   Promise<void>: 实体生成、验收和总览刷新完成后结束。
   */
  const createJob = async (
    payload: Omit<ImageryMosaicCreatePayload, 'operator_code'>,
  ): Promise<void> => {
    creatingRef.value = true
    try {
      await userStore.initialize(workbenchStore.projectCodeComputed)
      await createImageryMosaicJob(
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
        { ...payload, operator_code: requireUserCode() },
      )
      await load()
      await workbenchStore.refreshOverview()
    } finally {
      creatingRef.value = false
    }
  }

  /**
   * 下载一个通过实体复核的 GeoTIFF 镶嵌成果。
   * Args:
   *   jobCode: 镶嵌任务编号。
   *   filename: 服务端固化的原文件名。
   * Returns:
   *   Promise<void>: 浏览器下载触发后结束。
   */
  const downloadJob = async (
    jobCode: string,
    filename: string,
  ): Promise<void> => {
    downloadingJobCodeRef.value = jobCode
    try {
      await userStore.initialize(workbenchStore.projectCodeComputed)
      const blob = await downloadImageryMosaicJob(
        workbenchStore.projectCodeComputed,
        jobCode,
        requireUserCode(),
      )
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      link.click()
      URL.revokeObjectURL(url)
    } finally {
      downloadingJobCodeRef.value = null
    }
  }

  return {
    overviewRef,
    boundariesRef,
    loadingRef,
    creatingRef,
    downloadingJobCodeRef,
    canProcessComputed,
    load,
    createJob,
    downloadJob,
  }
})
