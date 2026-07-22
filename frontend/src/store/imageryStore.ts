import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  executeImageryProcessingStep,
  getImageryProcessing,
  runImageryProcessingStep,
} from '@/api/index'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  ImageryArtifactRegisterPayload,
  ImageryProcessing,
  ImageryStepExecutePayload,
} from '@/types/workbench'

export const useImageryStore = defineStore('imagery', () => {
  const workbenchStore = useWorkbenchStore()
  const userStore = useUserStore()
  const processingRef = ref<ImageryProcessing | null>(null)
  const loadingRef = ref<boolean>(false)
  const processingStepCodeRef = ref<string | null>(null)
  const canProcessComputed = computed<boolean>(() => (
    userStore.hasCapability('process_imagery')
  ))

  /**
   * 加载当前影像预处理流水线。
   * Args:
   *   无。
   * Returns:
   *   Promise<void>: 处理流水线加载完成后结束。
   */
  const load = async (assetCode?: string): Promise<void> => {
    loadingRef.value = true
    try {
      const targetAssetCode = assetCode
        || processingRef.value?.asset_code
        || workbenchStore.overviewRef?.imagery?.asset_code
      if (!targetAssetCode) {
        processingRef.value = null
        return
      }
      processingRef.value = await getImageryProcessing(targetAssetCode)
    } finally {
      loadingRef.value = false
    }
  }

  /**
   * 执行影像预处理步骤。
   * Args:
   *   stepCode: 处理步骤编号。
   *   payload: 实体产物相对路径、处理器和操作人。
   * Returns:
   *   Promise<void>: 处理步骤执行完成后结束。
   */
  const registerStep = async (
    stepCode: string,
    payload: Omit<ImageryArtifactRegisterPayload, 'operator_code'>,
  ): Promise<void> => {
    const user = userStore.currentUserComputed
    if (!user || !canProcessComputed.value) {
      throw new Error('当前项目身份无权登记影像处理产物')
    }
    if (!processingRef.value?.asset_code) {
      throw new Error('请先选择真实影像资产')
    }
    processingRef.value = await runImageryProcessingStep(
      processingRef.value.asset_code,
      stepCode,
      { ...payload, operator_code: user.user_code },
      workbenchStore.taskCodeComputed,
    )
    await workbenchStore.refreshOverview()
  }

  /**
   * 使用平台内置处理器执行当前影像步骤。
   * Args:
   *   stepCode: 标准处理步骤编号。
   *   parameters: 明确的算法、波段或边界参数。
   *   comment: 处理说明。
   * Returns:
   *   Promise<void>: 实体产物生成、校验和状态刷新完成后结束。
   */
  const executeStep = async (
    stepCode: string,
    parameters: ImageryStepExecutePayload['parameters'],
    comment: string | null,
  ): Promise<void> => {
    const user = userStore.currentUserComputed
    if (!user || !canProcessComputed.value) {
      throw new Error('当前项目身份无权执行影像预处理')
    }
    if (!processingRef.value?.asset_code) {
      throw new Error('请先选择真实影像资产')
    }
    processingStepCodeRef.value = stepCode
    try {
      processingRef.value = await executeImageryProcessingStep(
        processingRef.value.asset_code,
        stepCode,
        {
          operator_code: user.user_code,
          parameters,
          comment,
        },
        workbenchStore.taskCodeComputed,
      )
      await workbenchStore.refreshOverview()
    } finally {
      processingStepCodeRef.value = null
    }
  }

  return {
    processingRef,
    loadingRef,
    processingStepCodeRef,
    canProcessComputed,
    load,
    registerStep,
    executeStep,
  }
})
