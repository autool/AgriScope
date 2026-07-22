<script setup lang="ts">
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, reactive, ref, watch } from 'vue'

import ImageryGcpEditor from '@/components/imagery/ImageryGcpEditor.vue'
import { useImageryStore } from '@/store/imageryStore'
import { useLayerStore } from '@/store/layerStore'
import { useUserStore } from '@/store/userStore'
import type {
  ImageryGcpControlPointDraft,
  ImageryProcessingStep,
} from '@/types/workbench'

interface ImageryStepActionModalProps {
  open: boolean
  step: ImageryProcessingStep | null
  assetCode: string
  assetVerified: boolean
  assetBandCount: number | null
  assetBandDescriptions: Array<string | null>
  rasterWidth: number | null
  rasterHeight: number | null
  assetHasRpc: boolean
  processingLevel: string | null
  initialMode?: 'execute' | 'register' | 'source-accept'
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
const modeRef = ref<'execute' | 'register' | 'source-accept'>('execute')
const savingRef = ref<boolean>(false)
const sourceAcceptanceConfirmedRef = ref<boolean>(false)
const commentRef = ref<string>('')
const outputPathRef = ref<string>('')
const processorNameRef = ref<string>('外部遥感处理器')
const processorVersionRef = ref<string>('1.0')
const gcpPointsRef = ref<ImageryGcpControlPointDraft[]>([])
const rpcDemRelativePathRef = ref<string>('')
const parameters = reactive({
  scaleFactor: 0.0001,
  addOffset: 0,
  darkPercentile: 1,
  geometricMethod: 'reproject' as 'reproject' | 'gcp' | 'rpc_dem',
  targetCrs: 'EPSG:4490',
  targetResolution: null as number | null,
  resampling: 'bilinear' as 'nearest' | 'bilinear' | 'cubic',
  gcpCrs: 'EPSG:4326',
  maxRmsePixels: 2,
  rpcHeightOffsetM: 0,
  enhancementMethod: 'percentile_stretch' as (
    'percentile_stretch' | 'histogram_equalization'
  ),
  lowerPercentile: 2,
  upperPercentile: 98,
  histogramBins: 256,
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

const sourceAcceptanceEligibleComputed = computed<boolean>(() => (
  props.processingLevel?.toUpperCase() === 'L2A'
  && ['radiometric', 'atmospheric'].includes(props.step?.step_code || '')
))

const close = (): void => emit('update:open', false)

const executionParameters = (): Record<string, unknown> => {
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
    const common = {
      method: parameters.geometricMethod,
      target_crs: parameters.targetCrs.trim(),
      target_resolution: parameters.targetResolution,
      resampling: parameters.resampling,
    }
    if (parameters.geometricMethod === 'gcp') {
      return {
        ...common,
        gcp_crs: parameters.gcpCrs.trim(),
        max_rmse_pixels: parameters.maxRmsePixels,
        control_points: gcpPointsRef.value.map((point) => ({
          ...point,
          z: point.z ?? 0,
          point_id: point.point_id.trim(),
          source: point.source.trim(),
        })),
      }
    }
    if (parameters.geometricMethod === 'rpc_dem') {
      return {
        ...common,
        dem_relative_path: rpcDemRelativePathRef.value.trim(),
        rpc_height_offset_m: parameters.rpcHeightOffsetM,
      }
    }
    return common
  }
  if (stepCode === 'clip') {
    return { boundary_code: parameters.boundaryCode }
  }
  if (stepCode === 'enhancement') {
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
  if (
    modeRef.value === 'execute'
    && step.step_code === 'geometric'
    && parameters.geometricMethod === 'gcp'
  ) {
    if (gcpPointsRef.value.length < 3) {
      message.warning('GCP 精校正至少需要 3 个不共线控制点')
      return
    }
    const incompletePoint = gcpPointsRef.value.find((point) => (
      !point.point_id.trim()
      || point.pixel_column === null
      || point.pixel_row === null
      || point.x === null
      || point.y === null
      || !point.source.trim()
    ))
    if (incompletePoint) {
      message.warning(`请补全控制点 ${incompletePoint.point_id || '未编号点'} 的坐标和真实来源`)
      return
    }
    if (commentRef.value.trim().length < 10) {
      message.warning('请填写至少 10 个字符的控制点来源与精校正说明')
      return
    }
  }
  if (
    modeRef.value === 'execute'
    && step.step_code === 'enhancement'
    && parameters.enhancementMethod === 'percentile_stretch'
    && parameters.lowerPercentile >= parameters.upperPercentile
  ) {
    message.warning('拉伸下限百分位必须小于上限百分位')
    return
  }
  if (
    modeRef.value === 'execute'
    && step.step_code === 'geometric'
    && parameters.geometricMethod === 'rpc_dem'
  ) {
    if (!props.assetHasRpc) {
      message.warning('当前源影像没有内嵌 RPC 模型，不能执行 RPC/DEM 正射')
      return
    }
    if (!rpcDemRelativePathRef.value.trim()) {
      message.warning('请填写影像受控目录内的 DEM 实体相对路径')
      return
    }
    if (commentRef.value.trim().length < 10) {
      message.warning('请填写至少 10 个字符的 RPC、DEM 来源和正射说明')
      return
    }
  }
  if (modeRef.value === 'source-accept') {
    if (!sourceAcceptanceEligibleComputed.value) {
      message.warning('当前步骤或产品级别不支持源级承认')
      return
    }
    if (!sourceAcceptanceConfirmedRef.value) {
      message.warning('请确认本动作不会执行或伪造重复算法')
      return
    }
    if (commentRef.value.trim().length < 10) {
      message.warning('请填写至少 10 个字符的源产品承认依据')
      return
    }
  }
  savingRef.value = true
  try {
    if (modeRef.value === 'source-accept') {
      await imageryStore.acceptSourceLevelStep(step.step_code, {
        expected_processing_level: 'L2A',
        confirm_no_algorithm_execution: true,
        justification: commentRef.value.trim(),
      })
      emit('success', `${step.step_name}已通过 L2A 源产品证据承认`)
    } else if (modeRef.value === 'execute') {
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
    modeRef.value = (
      props.initialMode === 'source-accept'
      && !sourceAcceptanceEligibleComputed.value
    ) ? 'execute' : props.initialMode
    outputPathRef.value = `${props.assetCode}/${props.step.step_code}-result.tif`
    commentRef.value = ''
    sourceAcceptanceConfirmedRef.value = false
    parameters.geometricMethod = 'reproject'
    parameters.targetResolution = null
    parameters.resampling = 'bilinear'
    parameters.gcpCrs = 'EPSG:4326'
    parameters.maxRmsePixels = 2
    parameters.rpcHeightOffsetM = 0
    parameters.enhancementMethod = 'percentile_stretch'
    parameters.lowerPercentile = 2
    parameters.upperPercentile = 98
    parameters.histogramBins = 256
    rpcDemRelativePathRef.value = ''
    gcpPointsRef.value = Array.from({ length: 4 }, (_, index) => ({
      point_id: `GCP-${String(index + 1).padStart(2, '0')}`,
      pixel_column: null,
      pixel_row: null,
      x: null,
      y: null,
      z: 0,
      source: '',
    }))
    const normalizedDescriptions = props.assetBandDescriptions.map(
      (description) => description?.trim().toLowerCase() || '',
    )
    const bandIndex = (name: string, fallback: number): number => {
      const index = normalizedDescriptions.findIndex((item) => item === name)
      return index >= 0 ? index + 1 : fallback
    }
    parameters.redBand = bandIndex('red', 1)
    parameters.greenBand = bandIndex('green', 2)
    parameters.blueBand = bandIndex('blue', 3)
    parameters.nirBand = bandIndex('nir', 4)
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
    :width="props.step?.step_code === 'geometric' ? '960px' : '620px'"
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
          v-if="props.step?.output_verified"
          type="warning"
          show-icon
          message="重新执行会保留当前产物证据，并将全部下游步骤重置为待处理。"
        />
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
            <label><span>校正方法</span><a-select v-model:value="parameters.geometricMethod" :options="[{ value: 'reproject', label: '坐标系重投影' }, { value: 'gcp', label: 'GCP 仿射精校正' }, { value: 'rpc_dem', label: 'RPC + DEM 严格正射', disabled: !props.assetHasRpc }]" /></label>
            <label><span>目标坐标系</span><a-input v-model:value="parameters.targetCrs" placeholder="EPSG:4490" /></label>
            <label><span>目标分辨率</span><a-input-number v-model:value="parameters.targetResolution" :min="0.000000000001" placeholder="留空自动计算" /></label>
            <label><span>重采样</span><a-select v-model:value="parameters.resampling" :options="[{ value: 'nearest', label: '最近邻' }, { value: 'bilinear', label: '双线性' }, { value: 'cubic', label: '三次卷积' }]" /></label>
            <template v-if="parameters.geometricMethod === 'gcp'">
              <label><span>控制点坐标系</span><a-input v-model:value="parameters.gcpCrs" placeholder="EPSG:4326" /></label>
              <label><span>RMSE 门槛</span><a-input-number
                v-model:value="parameters.maxRmsePixels"
                :min="0"
                :max="100"
                addon-after="像素"
              /></label>
              <ImageryGcpEditor
                v-model:points="gcpPointsRef"
                :raster-width="props.rasterWidth"
                :raster-height="props.rasterHeight"
              />
            </template>
            <template v-else-if="parameters.geometricMethod === 'rpc_dem'">
              <a-alert
                class="wide-alert"
                type="warning"
                show-icon
                message="服务端将重新读取源影像 RPC 模型，校验 DEM 实体、SHA-256 与覆盖范围；普通 GeoTIFF 或仅填写路径不能冒充正射成果。"
              />
              <label class="wide"><span>DEM 相对路径</span><a-input v-model:value="rpcDemRelativePathRef" placeholder="dem/hlj-dem-30m.tif" /></label>
              <label><span>高程偏移</span><a-input-number
                v-model:value="parameters.rpcHeightOffsetM"
                :min="-10000"
                :max="10000"
                addon-after="米"
              /></label>
              <label><span>RPC 状态</span><strong>{{ props.assetHasRpc ? '源影像已登记 RPC' : '源影像缺少 RPC' }}</strong></label>
            </template>
          </template>
          <template v-else-if="props.step?.step_code === 'clip'">
            <label><span>真实行政区边界</span><a-select v-model:value="parameters.boundaryCode" show-search :options="boundaryOptionsComputed" /></label>
          </template>
          <template v-else-if="props.step?.step_code === 'enhancement'">
            <label><span>增强方法</span><a-select v-model:value="parameters.enhancementMethod" :options="[{ value: 'percentile_stretch', label: '百分位对比度拉伸' }, { value: 'histogram_equalization', label: '直方图均衡化' }]" /></label>
            <template v-if="parameters.enhancementMethod === 'percentile_stretch'">
              <label><span>下限百分位</span><a-input-number
                v-model:value="parameters.lowerPercentile"
                :min="0"
                :max="49.999"
                addon-after="%"
              /></label>
              <label><span>上限百分位</span><a-input-number
                v-model:value="parameters.upperPercentile"
                :min="50.001"
                :max="100"
                addon-after="%"
              /></label>
            </template>
            <label v-else><span>直方图分箱</span><a-input-number v-model:value="parameters.histogramBins" :min="32" :max="4096" /></label>
            <a-alert
              class="wide-alert"
              type="info"
              show-icon
              message="增强输出统一为 0–1 浮点栅格并保存每波段输入范围；执行后必须重新生成下游波段产品。"
            />
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
          v-if="props.step?.output_verified"
          type="warning"
          show-icon
          message="替换当前实体会保留旧产物证据，并将全部下游步骤重置为待处理。"
        />
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
      <a-tab-pane
        v-if="sourceAcceptanceEligibleComputed"
        key="source-accept"
        tab="L2A 源级承认"
      >
        <a-alert
          type="warning"
          show-icon
          message="服务端将重新核验源实体 SHA-256、L2A、STAC 标度应用、BOA 反射率及来源许可；不会复制文件，也不会执行 DOS1 等重复算法。"
        />
        <div class="source-acceptance-form">
          <p>
            适用步骤：{{ props.step?.step_name }}。承认后该步骤复用同一已校验实体，
            审计记录会明确标注“未执行算法”。
          </p>
          <a-checkbox v-model:checked="sourceAcceptanceConfirmedRef">
            我确认仅承认已存在的 Sentinel-2 L2A 产品能力，不把跳过描述为算法执行
          </a-checkbox>
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
.source-acceptance-form { padding: 14px; margin-top: 12px; font-size: 10px; line-height: 1.7; background: #f7f9f8; border: 1px solid #e0e7e3; border-radius: 6px; }
.common-form { padding-top: 12px; border-top: 1px solid #e7ebe9; }
.action-form label, .common-form label { display: grid; grid-template-columns: 130px minmax(0, 1fr); gap: 8px; align-items: center; font-size: 9px; }
.action-form label:has(.ant-select), .action-form .wide, .common-form label:last-child, .action-form > :deep(.ant-alert) { grid-column: 1 / -1; }
.action-form :deep(.ant-input-number), .action-form :deep(.ant-select) { width: 100%; }
</style>
