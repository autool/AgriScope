import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { getImageryAssets, uploadImageryAsset } from '@/api/index'
import { uploadImageryAssetBatch } from '@/api/imageryBatch'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  ImageryAssetCatalog,
  ImageryAssetItem,
} from '@/types/workbench'
import type {
  ImageryBatchManifest,
  ImageryBatchResponse,
} from '@/types/imageryBatch'

export interface ImageryUploadMetadata {
  assetCode: string
  assetName: string
  sensorType: string | null
  acquiredAt: string | null
  cloudCover: number | null
  processingLevel: string | null
  dataStatus: 'operational' | 'demo'
}

export const useAssetStore = defineStore('asset', () => {
  const workbenchStore = useWorkbenchStore()
  const userStore = useUserStore()
  const catalogRef = ref<ImageryAssetCatalog | null>(null)
  const loadingRef = ref<boolean>(false)
  const uploadingRef = ref<boolean>(false)
  const uploadProgressRef = ref<number>(0)
  const canManageComputed = computed<boolean>(() => (
    userStore.hasCapability('manage_imagery')
  ))

  /**
   * 加载项目影像资产目录。
   * Args:
   *   无。
   * Returns:
   *   Promise<void>: 资产目录加载完成后结束。
   */
  const load = async (): Promise<void> => {
    loadingRef.value = true
    try {
      catalogRef.value = await getImageryAssets(
        workbenchStore.projectCodeComputed,
      )
    } finally {
      loadingRef.value = false
    }
  }

  /**
   * 上传真实遥感影像并刷新资产目录。
   * Args:
   *   file: 用户选择的 GeoTIFF、IMG 或 HDF 文件。
   *   metadata: 资产编号、传感器和采集时间等业务元数据。
   * Returns:
   *   Promise<ImageryAssetItem>: 后端解析并入库的资产。
   */
  const upload = async (
    file: File,
    metadata: ImageryUploadMetadata,
  ): Promise<ImageryAssetItem> => {
    const user = userStore.currentUserComputed
    if (!user || !canManageComputed.value) {
      throw new Error('当前项目身份无权导入影像资产')
    }
    const formData = new FormData()
    formData.append('file', file)
    formData.append('asset_code', metadata.assetCode)
    formData.append('asset_name', metadata.assetName)
    formData.append('operator_code', user.user_code)
    if (metadata.sensorType) {
      formData.append('sensor_type', metadata.sensorType)
    }
    if (metadata.acquiredAt) {
      formData.append('acquired_at', metadata.acquiredAt)
    }
    if (metadata.cloudCover !== null) {
      formData.append('cloud_cover', String(metadata.cloudCover))
    }
    if (metadata.processingLevel) {
      formData.append('processing_level', metadata.processingLevel)
    }
    formData.append('data_status', metadata.dataStatus)
    uploadingRef.value = true
    uploadProgressRef.value = 0
    try {
      const asset = await uploadImageryAsset(
        formData,
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
        (progress) => { uploadProgressRef.value = progress },
      )
      await Promise.all([load(), workbenchStore.refreshOverview()])
      return asset
    } finally {
      uploadingRef.value = false
    }
  }

  /** 原子上传一个 1–20 个文件的影像批次并刷新项目状态。 */
  const uploadBatch = async (
    files: File[],
    manifest: Omit<ImageryBatchManifest, 'operator_code'>,
  ): Promise<ImageryBatchResponse> => {
    const user = userStore.currentUserComputed
    if (!user || !canManageComputed.value) {
      throw new Error('当前项目身份无权批量导入影像资产')
    }
    const formData = new FormData()
    files.forEach((file) => formData.append('files', file, file.name))
    formData.append('manifest_json', JSON.stringify({
      ...manifest,
      operator_code: user.user_code,
    }))
    uploadingRef.value = true
    uploadProgressRef.value = 0
    try {
      const batch = await uploadImageryAssetBatch(
        formData,
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
        (progress) => { uploadProgressRef.value = progress },
      )
      await Promise.all([load(), workbenchStore.refreshOverview()])
      return batch
    } finally {
      uploadingRef.value = false
    }
  }

  return {
    catalogRef,
    loadingRef,
    uploadingRef,
    uploadProgressRef,
    canManageComputed,
    load,
    upload,
    uploadBatch,
  }
})
