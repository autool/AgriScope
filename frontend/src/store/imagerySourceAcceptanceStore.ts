import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { acceptImagerySourceLevelBatch } from '@/api/imagerySourceAcceptance'
import { useAssetStore } from '@/store/assetStore'
import { useImageryStore } from '@/store/imageryStore'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  ImagerySourceAcceptanceBatchResponse,
  ImagerySourceProcessingLevel,
} from '@/types/imagerySourceAcceptance'
import type { ImageryAssetItem } from '@/types/workbench'

export const useImagerySourceAcceptanceStore = defineStore(
  'imagerySourceAcceptance',
  () => {
    const MAX_BATCH_ITEMS = 10
    const assetStore = useAssetStore()
    const imageryStore = useImageryStore()
    const userStore = useUserStore()
    const workbenchStore = useWorkbenchStore()
    const selectedAssetCodesRef = ref<string[]>([])
    const justificationRef = ref<string>('')
    const confirmationRef = ref<boolean>(false)
    const acceptingRef = ref<boolean>(false)
    const errorRef = ref<string | null>(null)
    const lastResultRef = ref<ImagerySourceAcceptanceBatchResponse | null>(null)
    const canProcessComputed = computed<boolean>(() => (
      userStore.hasCapability('process_imagery')
    ))
    const eligibleAssetsComputed = computed<ImageryAssetItem[]>(() => (
      (assetStore.catalogRef?.items || []).filter(asset => (
        asset.data_status === 'operational'
        && asset.file_verified
        && ['L2A', 'L2'].includes(asset.processing_level?.toUpperCase() || '')
        && asset.calibration_status !== 'completed'
        && asset.correction_status === 'pending'
      ))
    ))
    const selectedAssetsComputed = computed<ImageryAssetItem[]>(() => (
      eligibleAssetsComputed.value.filter(asset => (
        selectedAssetCodesRef.value.includes(asset.asset_code)
      ))
    ))
    const validationMessagesComputed = computed<string[]>(() => {
      const messages: string[] = []
      if (!canProcessComputed.value) {
        messages.push('当前项目身份无权承认影像源产品级别')
      }
      if (selectedAssetsComputed.value.length === 0) {
        messages.push('请至少选择一景待处理 L2A/L2 业务影像')
      }
      if (selectedAssetsComputed.value.length > MAX_BATCH_ITEMS) {
        messages.push(`单批最多选择 ${MAX_BATCH_ITEMS} 景影像`)
      }
      if (justificationRef.value.trim().length < 10) {
        messages.push('源级承认依据至少填写 10 个字符')
      }
      if (!confirmationRef.value) {
        messages.push('必须确认本批次不执行或伪造重复算法')
      }
      return messages
    })
    const canSubmitComputed = computed<boolean>(() => (
      !acceptingRef.value && validationMessagesComputed.value.length === 0
    ))

    /** 打开工作台时刷新真实资产目录并清空上一次未提交选择。 */
    const initialize = async (): Promise<void> => {
      errorRef.value = null
      selectedAssetCodesRef.value = []
      justificationRef.value = ''
      confirmationRef.value = false
      lastResultRef.value = null
      await assetStore.load()
    }

    /** 切换一个待处理源产品，最多保留十景显式选择。 */
    const toggleAsset = (assetCode: string): void => {
      if (!eligibleAssetsComputed.value.some(asset => asset.asset_code === assetCode)) {
        throw new Error('当前影像不满足双步骤源级批次候选条件')
      }
      if (selectedAssetCodesRef.value.includes(assetCode)) {
        selectedAssetCodesRef.value = selectedAssetCodesRef.value.filter(
          code => code !== assetCode,
        )
        return
      }
      if (selectedAssetCodesRef.value.length >= MAX_BATCH_ITEMS) {
        throw new Error(`单批最多选择 ${MAX_BATCH_ITEMS} 景影像`)
      }
      selectedAssetCodesRef.value = [...selectedAssetCodesRef.value, assetCode]
    }

    /** 一次提交全部影像的定标与大气校正源级承认。 */
    const acceptBatch = async (): Promise<ImagerySourceAcceptanceBatchResponse> => {
      const user = userStore.currentUserComputed
      if (!user || !canProcessComputed.value) {
        throw new Error('当前项目身份无权承认影像源产品级别')
      }
      if (validationMessagesComputed.value.length) {
        throw new Error(validationMessagesComputed.value[0])
      }
      acceptingRef.value = true
      errorRef.value = null
      try {
        const response = await acceptImagerySourceLevelBatch(
          {
            operator_code: user.user_code,
            confirm_no_algorithm_execution: true,
            justification: justificationRef.value.trim(),
            items: selectedAssetsComputed.value.map(asset => ({
              asset_code: asset.asset_code,
              expected_processing_level: (
                asset.processing_level?.toUpperCase()
              ) as ImagerySourceProcessingLevel,
            })),
          },
          workbenchStore.taskCodeComputed,
        )
        lastResultRef.value = response
        await Promise.all([
          assetStore.load(),
          workbenchStore.refreshOverview(),
        ])
        if (
          imageryStore.processingRef?.asset_code
          && response.items.some(
            item => item.asset_code === imageryStore.processingRef?.asset_code,
          )
        ) {
          await imageryStore.load(imageryStore.processingRef.asset_code)
        }
        return response
      } catch (error) {
        errorRef.value = error instanceof Error
          ? error.message
          : '多景源产品级别承认失败'
        throw error
      } finally {
        acceptingRef.value = false
      }
    }

    return {
      selectedAssetCodesRef,
      justificationRef,
      confirmationRef,
      acceptingRef,
      errorRef,
      lastResultRef,
      canProcessComputed,
      eligibleAssetsComputed,
      selectedAssetsComputed,
      validationMessagesComputed,
      canSubmitComputed,
      maxBatchItems: MAX_BATCH_ITEMS,
      initialize,
      toggleAsset,
      acceptBatch,
    }
  },
)
