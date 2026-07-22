import { defineStore } from 'pinia'
import { ref } from 'vue'

import {
  createProductionBatch,
  createProductionWorkPackages,
  getProductionOverview,
  registerDatasetAsset,
  updateProductionBatchStatus,
  updateProductionWorkPackage,
} from '@/api/production'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  DatasetAssetCreatePayload,
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
    createBatch,
    createPackages,
    updateBatchStatus,
    updatePackage,
  }
})
