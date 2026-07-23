import { defineStore } from 'pinia'
import { ref } from 'vue'

import {
  createProductionBatch,
  createProductionWorkPackages,
  downloadDatasetAsset,
  getProductionOverview,
  registerDatasetAsset,
  uploadDatasetAsset,
  uploadDatasetAssetBatch,
  updateProductionBatchStatus,
  updateProductionWorkPackage,
  verifyDatasetAsset,
} from '@/api/production'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  DatasetAssetCreatePayload,
  DatasetAssetBatchCreatePayload,
  DatasetAssetBatchResult,
  DatasetAssetUploadPayload,
  DatasetAssetVerificationResult,
  ProductionBatchCreatePayload,
  ProductionBatchStatus,
  ProductionOverview,
  WorkPackageCreatePayload,
  WorkPackageCreateResult,
  WorkPackageUpdatePayload,
} from '@/types/production'

export const useProductionStore = defineStore('production', () => {
  const workbenchStore = useWorkbenchStore()
  const overviewRef = ref<ProductionOverview | null>(null)
  const loadingRef = ref<boolean>(false)
  const savingRef = ref<boolean>(false)

  /** 加载生产调度和多源数据目录。 */
  const load = async (): Promise<void> => {
    loadingRef.value = true
    try {
      overviewRef.value = await getProductionOverview(
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
      )
    } finally {
      loadingRef.value = false
    }
  }

  /** 登记资产后刷新聚合状态。 */
  const registerAsset = async (payload: DatasetAssetCreatePayload): Promise<void> => {
    savingRef.value = true
    try {
      await registerDatasetAsset(
        payload,
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
      )
      await load()
    } finally {
      savingRef.value = false
    }
  }

  /** 上传实体登记后刷新目录聚合状态。 */
  const uploadAsset = async (
    payload: DatasetAssetUploadPayload,
    file: File,
  ): Promise<void> => {
    savingRef.value = true
    try {
      await uploadDatasetAsset(
        payload,
        file,
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
      )
      await load()
    } finally {
      savingRef.value = false
    }
  }

  /** 原子导入多文件数据资产批次并刷新目录。 */
  const uploadAssetBatch = async (
    payload: DatasetAssetBatchCreatePayload,
    files: File[],
  ): Promise<DatasetAssetBatchResult> => {
    savingRef.value = true
    try {
      const result = await uploadDatasetAssetBatch(
        payload,
        files,
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
      )
      await load()
      return result
    } finally {
      savingRef.value = false
    }
  }

  /** 补传资产实体并返回服务端核验结论。 */
  const verifyAsset = async (
    assetCode: string,
    file: File,
    operatorCode: string,
    verificationComment: string,
  ): Promise<DatasetAssetVerificationResult> => {
    savingRef.value = true
    try {
      const result = await verifyDatasetAsset(
        assetCode,
        file,
        operatorCode,
        verificationComment,
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
      )
      await load()
      return result
    } finally {
      savingRef.value = false
    }
  }

  /** 下载已在服务端重新复核的数据资产实体。 */
  const downloadAsset = async (
    assetCode: string,
    operatorCode: string,
  ): Promise<Blob> => downloadDatasetAsset(
    assetCode,
    operatorCode,
    workbenchStore.projectCodeComputed,
    workbenchStore.taskCodeComputed,
  )

  /** 创建生产批次后刷新调度状态。 */
  const createBatch = async (payload: ProductionBatchCreatePayload): Promise<void> => {
    savingRef.value = true
    try {
      await createProductionBatch(
        payload,
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
      )
      await load()
    } finally {
      savingRef.value = false
    }
  }

  /** 创建显式县区作业包后刷新调度状态。 */
  const createPackages = async (
    batchCode: string,
    payload: WorkPackageCreatePayload,
  ): Promise<WorkPackageCreateResult> => {
    savingRef.value = true
    try {
      const result = await createProductionWorkPackages(
        batchCode,
        payload,
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
      )
      await load()
      return result
    } finally {
      savingRef.value = false
    }
  }

  /** 流转批次状态并刷新聚合状态。 */
  const updateBatchStatus = async (
    batchCode: string,
    status: ProductionBatchStatus,
    operatorCode: string,
  ): Promise<void> => {
    savingRef.value = true
    try {
      await updateProductionBatchStatus(
        batchCode,
        status,
        operatorCode,
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
      )
      await load()
    } finally {
      savingRef.value = false
    }
  }

  /** 更新作业包调度字段并刷新聚合状态。 */
  const updatePackage = async (
    packageCode: string,
    payload: WorkPackageUpdatePayload,
  ): Promise<void> => {
    savingRef.value = true
    try {
      await updateProductionWorkPackage(
        packageCode,
        payload,
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
      )
      await load()
    } finally {
      savingRef.value = false
    }
  }

  return {
    overviewRef,
    loadingRef,
    savingRef,
    load,
    registerAsset,
    uploadAsset,
    uploadAssetBatch,
    verifyAsset,
    downloadAsset,
    createBatch,
    createPackages,
    updateBatchStatus,
    updatePackage,
  }
})
