<script setup lang="ts">
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, reactive, ref, watch } from 'vue'

import { useImageryStore } from '@/store/imageryStore'
import { useLayerStore } from '@/store/layerStore'
import { useUserStore } from '@/store/userStore'
import type { ImageryProcessingStep } from '@/types/workbench'

interface ImageryStepActionModalProps {
  open: boolean
  step: ImageryProcessingStep | null
  assetCode: string
  assetVerified: boolean
  assetBandCount: number | null
  initialMode?: 'execute' | 'register'
}

const props = withDefaults(defineProps<ImageryStepActionModalProps>(), {
  initialMode: 'execute',
})
const emit = defineEmits<{
  'update:open': [value: boolean]
  success: [message: string]
}>()

const imageryStore = useImageryStore()
const layerStore = useLayerStore()
const userStore = useUserStore()
const { canProcessComputed } = storeToRefs(imageryStore)
const modeRef = ref<'execute' | 'register'>('execute')
const savingRef = ref<boolean>(false)
const commentRef = ref<string>('')
const outputPathRef = ref<string>('')
const processorNameRef = ref<string>('外部遥感处理器')
const processorVersionRef = ref<string>('1.0')
const parameters = reactive({
  scaleFactor: 0.0001,
  addOffset: 0,
  darkPercentile: 1,
  targetCrs: 'EPSG:4490',
  boundaryCode: '230000',
  redBand: 1,
  greenBand: 2,
  blueBand: 3,
  nirBand: 4,
})

const boundaryOptionsComputed = computed(() => (
  layerStore.boundaryFeaturesRef.features.map((feature) => ({
    value: feature.properties.boundary_code,
    label: `${{
      province: '省级',
      city: '地级',
      district: '县级',
      township: '乡级',
    }[feature.properties.boundary_level]} · ${feature.properties.boundary_name}`,
  }))
))

const capabilityTextComputed = computed<string>(() => (
  canProcessComputed.value
    ? `${userStore.currentUserComputed?.display_name || '--'} · ${userStore.currentUserComputed?.role_name || '--'}`
    : '当前身份无影像处理权限'
))

const close = (): void => emit('update:open', false)

const executionParameters = (): Record<string, string | number> => {
  const stepCode = props.step?.step_code
  if (stepCode === 'radiometric') {
    return {
      scale_factor: parameters.scaleFactor,
      add_offset: parameters.addOffset,
    }
  }
  if (stepCode === 'atmospheric') {
    return { dark_percentile: parameters.darkPercentile }
  }
  if (stepCode === 'geometric') {
    return { target_crs: parameters.targetCrs.trim() }
  }
  if (stepCode === 'clip') {
    return { boundary_code: parameters.boundaryCode }
  }
  if (stepCode === 'band_products') {
    return {
      red_band: parameters.redBand,
      green_band: parameters.greenBand,
      blue_band: parameters.blueBand,
      nir_band: parameters.nirBand,
    }
  }
  return {}
}

/**
 * 执行平台处理或登记外部实体产物。
 * Args:
 *   无。
 * Returns:
 *   Promise<void>: 产物校验和流水线刷新完成后结束。
 */
const submit = async (): Promise<void> => {
  const step = props.step
  if (!step) return
  if (!canProcessComputed.value) {
    message.warning('当前项目身份无权执行影像预处理')
    return
  }
  if (modeRef.value === 'execute' && !props.assetVerified) {
    message.warning('当前影像没有可用实体源文件，不能由平台执行')
    return
  }
  if (modeRef.value === 'register' && !outputPathRef.value.trim()) {
    message.warning('请填写影像存储目录内的产物相对路径')
    return
  }
  savingRef.value = true
  try {
    if (modeRef.value === 'execute') {
      await imageryStore.executeStep(
        step.step_code,
        executionParameters(),
        commentRef.value.trim() || null,
      )
      emit('success', `${step.step_name}已生成平台处理实体产物`)
    } else {
      await imageryStore.registerStep(step.step_code, {
        output_relative_path: outputPathRef.value.trim(),
        processor_name: processorNameRef.value.trim(),
        processor_version: processorVersionRef.value.trim(),
        comment: commentRef.value.trim() || null,
      })
      emit('success', `${step.step_name}外部实体产物已通过校验`)
    }
    close()
  } catch {
    // 请求拦截器已展示安全错误，保留表单便于修正后重试。
  } finally {
    savingRef.value = false
  }
}

watch(
  () => [props.open, props.step?.step_code, props.initialMode] as const,
  ([open]) => {
    if (!open || !props.step) return
    modeRef.value = props.initialMode
    outputPathRef.value = `${props.assetCode}/${props.step.step_code}-result.tif`
    commentRef.value = ''
  },
  { immediate: true },
)
</script>

<template>
  <a-modal
    :open="props.open"
    :title="`${props.step?.step_name || '影像处理'} · 实体产物`"
    :confirm-loading="savingRef"
    ok-text="确认执行"
    cancel-text="取消"
    width="620px"
    @update:open="emit('update:open', $event)"
    @ok="submit"
  >
    <a-alert
      v-if="!canProcessComputed"
      type="warning"
      show-icon
      message="当前身份仅可查看处理流水线"
    />
    <a-tabs v-model:active-key="modeRef">
      <a-tab-pane key="execute" tab="平台执行">
        <a-alert
          type="info"
          show-icon
          message="平台将按下列明确参数执行 Rasterio 算法，并原子写入 GeoTIFF、计算 SHA-256。"
        />
        <div class="action-form">
          <template v-if="props.step?.step_code === 'radiometric'">
            <label><span>比例系数</span><a-input-number v-model:value="parameters.scaleFactor" :min="0.000000000001" :max="10" /></label>
            <label><span>加性偏移</span><a-input-number v-model:value="parameters.addOffset" :min="-1000" :max="1000" /></label>
          </template>
          <template v-else-if="props.step?.step_code === 'atmospheric'">
            <label><span>DOS1 暗目标百分位</span><a-input-number
              v-model:value="parameters.darkPercentile"
              :min="0"
              :max="10"
              addon-after="%"
            /></label>
          </template>
          <template v-else-if="props.step?.step_code === 'geometric'">
            <label><span>目标坐标系</span><a-input v-model:value="parameters.targetCrs" placeholder="EPSG:4490" /></label>
          </template>
          <template v-else-if="props.step?.step_code === 'clip'">
            <label><span>真实行政区边界</span><a-select v-model:value="parameters.boundaryCode" show-search :options="boundaryOptionsComputed" /></label>
          </template>
          <template v-else-if="props.step?.step_code === 'band_products'">
            <a-alert
              v-if="(props.assetBandCount || 0) < 4"
              type="warning"
              show-icon
              message="当前资产少于四波段，无法生成 NDVI。"
            />
            <label><span>红波段</span><a-input-number v-model:value="parameters.redBand" :min="1" :max="props.assetBandCount || 1" /></label>
            <label><span>绿波段</span><a-input-number v-model:value="parameters.greenBand" :min="1" :max="props.assetBandCount || 1" /></label>
            <label><span>蓝波段</span><a-input-number v-model:value="parameters.blueBand" :min="1" :max="props.assetBandCount || 1" /></label>
            <label><span>近红外波段</span><a-input-number v-model:value="parameters.nirBand" :min="1" :max="props.assetBandCount || 1" /></label>
          </template>
        </div>
      </a-tab-pane>
      <a-tab-pane key="register" tab="登记外部产物">
        <a-alert
          type="info"
          show-icon
          message="产物必须已放入 backend/storage/imagery，服务端将校验文件格式、大小和 SHA-256。"
        />
        <div class="action-form">
          <label><span>产物相对路径</span><a-input v-model:value="outputPathRef" /></label>
          <label><span>处理器名称</span><a-input v-model:value="processorNameRef" /></label>
          <label><span>处理器版本</span><a-input v-model:value="processorVersionRef" /></label>
        </div>
      </a-tab-pane>
    </a-tabs>
    <div class="common-form">
      <label><span>操作身份</span><strong>{{ capabilityTextComputed }}</strong></label>
      <label><span>处理说明</span><a-textarea v-model:value="commentRef" :rows="2" /></label>
    </div>
  </a-modal>
</template>

<style scoped>
.action-form, .common-form { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 14px; }
.common-form { padding-top: 12px; border-top: 1px solid #e7ebe9; }
.action-form label, .common-form label { display: grid; grid-template-columns: 130px minmax(0, 1fr); gap: 8px; align-items: center; font-size: 9px; }
.action-form label:has(.ant-select), .common-form label:last-child, .action-form > :deep(.ant-alert) { grid-column: 1 / -1; }
.action-form :deep(.ant-input-number), .action-form :deep(.ant-select) { width: 100%; }
</style>
