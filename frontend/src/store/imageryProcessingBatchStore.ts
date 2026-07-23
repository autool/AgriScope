import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { getAdministrativeBoundaries, getImageryProcessing } from '@/api/index'
import { executeImageryProcessingBatch } from '@/api/imageryProcessingBatch'
import { useAssetStore } from '@/store/assetStore'
import { useImageryStore } from '@/store/imageryStore'
import { useLayerStore } from '@/store/layerStore'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  ImageryProcessingBatchParameters,
  ImageryProcessingBatchResponse,
  ImageryProcessingBatchStepCode,
} from '@/types/imageryProcessingBatch'
import type {
  ImageryAssetItem,
  ImageryProcessing,
  ImageryProcessingStep,
} from '@/types/workbench'

export interface ImageryProcessingBatchCandidate {
  asset: ImageryAssetItem
  processing: ImageryProcessing | null
  targetStep: ImageryProcessingStep | null
  eligible: boolean
  blocker: string | null
}

const DEFAULT_PARAMETERS: ImageryProcessingBatchParameters = {
  scaleFactor: 0.0001,
  addOffset: 0,
  darkPercentile: 1,
  targetCrs: 'EPSG:4490',
  targetResolution: null,
  resampling: 'bilinear',
  boundaryCode: '230100',
  enhancementMethod: 'percentile_stretch',
  lowerPercentile: 2,
  upperPercentile: 98,
  histogramBins: 256,
  redBand: 3,
  greenBand: 2,
  blueBand: 1,
  nirBand: 4,
}

export const useImageryProcessingBatchStore = defineStore(
  'imageryProcessingBatch',
  () => {
    const MAX_BATCH_ITEMS = 10
    const assetStore = useAssetStore()
    const imageryStore = useImageryStore()
    const layerStore = useLayerStore()
    const userStore = useUserStore()
    const workbenchStore = useWorkbenchStore()
    const stepCodeRef = ref<ImageryProcessingBatchStepCode>('geometric')
    const selectedAssetCodesRef = ref<string[]>([])
    const processingByAssetCodeRef = ref<Record<string, ImageryProcessing>>({})
    const processingErrorsRef = ref<Record<string, string>>({})
    const parametersRef = ref<ImageryProcessingBatchParameters>({
      ...DEFAULT_PARAMETERS,
    })
    const commentRef = ref<string>('')
    const loadingRef = ref<boolean>(false)
    const executingRef = ref<boolean>(false)
    const errorRef = ref<string | null>(null)
    const lastResultRef = ref<ImageryProcessingBatchResponse | null>(null)
    const canProcessComputed = computed<boolean>(() => (
      userStore.hasCapability('process_imagery')
    ))

    const buildCandidate = (
      asset: ImageryAssetItem,
      stepCode: ImageryProcessingBatchStepCode,
    ): ImageryProcessingBatchCandidate => {
      const processing = processingByAssetCodeRef.value[asset.asset_code] || null
      const targetStep = processing?.steps.find(
        step => step.step_code === stepCode,
      ) || null
      let blocker: string | null = null
      if (asset.data_status !== 'operational') {
        blocker = '明确演示影像不得进入业务批处理'
      } else if (!asset.file_verified) {
        blocker = asset.file_error || '源影像实体未通过校验'
      } else if (processingErrorsRef.value[asset.asset_code]) {
        blocker = processingErrorsRef.value[asset.asset_code]
      } else if (!processing || !targetStep) {
        blocker = '未读取到完整处理流水线'
      } else if (targetStep.output_verified) {
        blocker = '该步骤已有有效产物；批量重跑需改用单景流程'
      } else {
        const dependency = processing.steps.find(step => (
          step.sequence < targetStep.sequence
          && step.is_required
          && !step.output_verified
        ))
        if (dependency) blocker = `请先完成 ${dependency.step_name}`
      }
      return {
        asset,
        processing,
        targetStep,
        eligible: blocker === null,
        blocker,
      }
    }

    const candidateRowsComputed = computed<ImageryProcessingBatchCandidate[]>(() => (
      (assetStore.catalogRef?.items || []).map(
        asset => buildCandidate(asset, stepCodeRef.value),
      )
    ))
    const eligibleCandidatesComputed = computed(() => (
      candidateRowsComputed.value.filter(candidate => candidate.eligible)
    ))
    const selectedCandidatesComputed = computed(() => (
      eligibleCandidatesComputed.value.filter(candidate => (
        selectedAssetCodesRef.value.includes(candidate.asset.asset_code)
      ))
    ))

    const getBandIndex = (
      asset: ImageryAssetItem,
      description: string,
      fallback: number,
    ): number => {
      const index = (asset.raster_metadata.descriptions || []).findIndex(
        item => item?.trim().toLowerCase() === description,
      )
      return index >= 0 ? index + 1 : fallback
    }

    const buildParameters = (asset: ImageryAssetItem): Record<string, unknown> => {
      const parameters = parametersRef.value
      if (stepCodeRef.value === 'radiometric') {
        return {
          scale_factor: parameters.scaleFactor,
          add_offset: parameters.addOffset,
        }
      }
      if (stepCodeRef.value === 'atmospheric') {
        return { dark_percentile: parameters.darkPercentile }
      }
      if (stepCodeRef.value === 'geometric') {
        return {
          method: 'reproject',
          target_crs: parameters.targetCrs.trim(),
          target_resolution: parameters.targetResolution,
          resampling: parameters.resampling,
        }
      }
      if (stepCodeRef.value === 'clip') {
        return { boundary_code: parameters.boundaryCode }
      }
      if (stepCodeRef.value === 'enhancement') {
        return parameters.enhancementMethod === 'percentile_stretch'
          ? {
              method: parameters.enhancementMethod,
              lower_percentile: parameters.lowerPercentile,
              upper_percentile: parameters.upperPercentile,
            }
          : {
              method: parameters.enhancementMethod,
              histogram_bins: parameters.histogramBins,
            }
      }
      return {
        red_band: getBandIndex(asset, 'red', parameters.redBand),
        green_band: getBandIndex(asset, 'green', parameters.greenBand),
        blue_band: getBandIndex(asset, 'blue', parameters.blueBand),
        nir_band: getBandIndex(asset, 'nir', parameters.nirBand),
      }
    }

    const validationMessagesComputed = computed<string[]>(() => {
      const messages: string[] = []
      if (!canProcessComputed.value) {
        messages.push('当前项目身份无权执行影像批处理')
      }
      if (selectedCandidatesComputed.value.length === 0) {
        messages.push('请至少选择一景满足当前步骤依赖的业务影像')
      }
      if (selectedCandidatesComputed.value.length > MAX_BATCH_ITEMS) {
        messages.push(`单批最多选择 ${MAX_BATCH_ITEMS} 景影像`)
      }
      if (commentRef.value.trim().length < 10) {
        messages.push('批次处理依据至少填写 10 个字符')
      }
      if (stepCodeRef.value === 'geometric' && !parametersRef.value.targetCrs.trim()) {
        messages.push('几何校正必须填写目标坐标系')
      }
      if (stepCodeRef.value === 'clip' && !parametersRef.value.boundaryCode) {
        messages.push('行政区裁剪必须选择真实边界')
      }
      if (
        stepCodeRef.value === 'enhancement'
        && parametersRef.value.enhancementMethod === 'percentile_stretch'
        && parametersRef.value.lowerPercentile >= parametersRef.value.upperPercentile
      ) {
        messages.push('增强拉伸下限百分位必须小于上限百分位')
      }
      if (stepCodeRef.value === 'band_products') {
        for (const candidate of selectedCandidatesComputed.value) {
          const mapping = buildParameters(candidate.asset)
          const indexes = [
            Number(mapping.red_band),
            Number(mapping.green_band),
            Number(mapping.blue_band),
            Number(mapping.nir_band),
          ]
          if (new Set(indexes).size !== 4) {
            messages.push(`资产 ${candidate.asset.asset_code} 的光谱角色必须映射到四个不同波段`)
            break
          }
          if (indexes.some(index => index < 1 || index > (candidate.asset.band_count || 0))) {
            messages.push(`资产 ${candidate.asset.asset_code} 的波段映射超过实体波段数量`)
            break
          }
        }
      }
      return messages
    })
    const canSubmitComputed = computed<boolean>(() => (
      !loadingRef.value
      && !executingRef.value
      && validationMessagesComputed.value.length === 0
    ))

    /** 读取真实资产、行政边界和每景处理流水线。 */
    const initialize = async (): Promise<void> => {
      selectedAssetCodesRef.value = []
      processingByAssetCodeRef.value = {}
      processingErrorsRef.value = {}
      parametersRef.value = { ...DEFAULT_PARAMETERS }
      commentRef.value = ''
      errorRef.value = null
      lastResultRef.value = null
      loadingRef.value = true
      try {
        const [, boundaries] = await Promise.all([
          assetStore.load(),
          getAdministrativeBoundaries(workbenchStore.projectCodeComputed),
        ])
        layerStore.setBoundaryFeatures(boundaries)
        const assets = (assetStore.catalogRef?.items || []).filter(
          asset => asset.data_status === 'operational' && asset.file_verified,
        )
        const results = await Promise.allSettled(
          assets.map(asset => getImageryProcessing(asset.asset_code)),
        )
        const processing: Record<string, ImageryProcessing> = {}
        const errors: Record<string, string> = {}
        results.forEach((result, index) => {
          const assetCode = assets[index].asset_code
          if (result.status === 'fulfilled') {
            processing[assetCode] = result.value
          } else {
            errors[assetCode] = result.reason instanceof Error
              ? result.reason.message
              : '处理流水线加载失败'
          }
        })
        processingByAssetCodeRef.value = processing
        processingErrorsRef.value = errors
        const preferredStep = ([
          'geometric',
          'clip',
          'enhancement',
          'band_products',
          'radiometric',
          'atmospheric',
        ] satisfies ImageryProcessingBatchStepCode[]).find(stepCode => (
          (assetStore.catalogRef?.items || []).some(
            asset => buildCandidate(asset, stepCode).eligible,
          )
        ))
        if (preferredStep) stepCodeRef.value = preferredStep
      } catch (error) {
        errorRef.value = error instanceof Error
          ? error.message
          : '影像批处理候选加载失败'
        throw error
      } finally {
        loadingRef.value = false
      }
    }

    /** 切换批处理步骤并清空旧步骤选择。 */
    const selectStep = (stepCode: ImageryProcessingBatchStepCode): void => {
      stepCodeRef.value = stepCode
      selectedAssetCodesRef.value = []
      errorRef.value = null
      lastResultRef.value = null
    }

    /** 显式选择或取消一个满足前置门禁的影像资产。 */
    const toggleAsset = (assetCode: string): void => {
      const candidate = eligibleCandidatesComputed.value.find(
        item => item.asset.asset_code === assetCode,
      )
      if (!candidate) throw new Error('当前影像不满足所选步骤的前置门禁')
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

    /** 一次提交全部成员并在成功后同步资产、流水线和总览。 */
    const executeBatch = async (): Promise<ImageryProcessingBatchResponse> => {
      const user = userStore.currentUserComputed
      if (!user || !canProcessComputed.value) {
        throw new Error('当前项目身份无权执行影像批处理')
      }
      if (validationMessagesComputed.value.length) {
        throw new Error(validationMessagesComputed.value[0])
      }
      executingRef.value = true
      errorRef.value = null
      try {
        const response = await executeImageryProcessingBatch(
          {
            operator_code: user.user_code,
            step_code: stepCodeRef.value,
            comment: commentRef.value.trim(),
            items: selectedCandidatesComputed.value.map(candidate => ({
              asset_code: candidate.asset.asset_code,
              parameters: buildParameters(candidate.asset),
            })),
          },
          workbenchStore.taskCodeComputed,
        )
        lastResultRef.value = response
        await Promise.all([
          assetStore.load(),
          workbenchStore.refreshOverview(),
        ])
        const refreshed = await Promise.all(
          response.items.map(item => getImageryProcessing(item.asset_code)),
        )
        processingByAssetCodeRef.value = {
          ...processingByAssetCodeRef.value,
          ...Object.fromEntries(refreshed.map(item => [item.asset_code, item])),
        }
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
          : '多景影像原子处理失败'
        throw error
      } finally {
        executingRef.value = false
      }
    }

    return {
      stepCodeRef,
      selectedAssetCodesRef,
      parametersRef,
      commentRef,
      loadingRef,
      executingRef,
      errorRef,
      lastResultRef,
      canProcessComputed,
      candidateRowsComputed,
      eligibleCandidatesComputed,
      selectedCandidatesComputed,
      validationMessagesComputed,
      canSubmitComputed,
      maxBatchItems: MAX_BATCH_ITEMS,
      initialize,
      selectStep,
      toggleAsset,
      buildParameters,
      executeBatch,
    }
  },
)
