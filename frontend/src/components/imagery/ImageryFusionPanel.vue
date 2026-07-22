<script setup lang="ts">
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, reactive, watch } from 'vue'

import { useImageryFusionStore } from '@/store/imageryFusionStore'
import type {
  ImageryFusionResamplingMethod,
  ImageryFusionSource,
} from '@/types/imageryFusion'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ 'update:open': [value: boolean] }>()

interface FusionFormState {
  jobCode: string
  jobName: string
  multispectralAssetCode: string
  panchromaticAssetCode: string
  multispectralBandIndexes: number[]
  panchromaticBandIndex: number
  resamplingMethod: ImageryFusionResamplingMethod
  minimumOverlapRatio: number
  minimumSpectralCorrelation: number
  minimumSpatialDetailGain: number
  gainLimit: number
  comment: string
}

const fusionStore = useImageryFusionStore()
const {
  overviewRef,
  loadingRef,
  creatingRef,
  downloadingJobCodeRef,
  canProcessComputed,
} = storeToRefs(fusionStore)

const form = reactive<FusionFormState>({
  jobCode: '',
  jobName: '',
  multispectralAssetCode: '',
  panchromaticAssetCode: '',
  multispectralBandIndexes: [],
  panchromaticBandIndex: 1,
  resamplingMethod: 'cubic',
  minimumOverlapRatio: 0.95,
  minimumSpectralCorrelation: 0.8,
  minimumSpatialDetailGain: 1.05,
  gainLimit: 4,
  comment: '',
})

const multispectralSourcesComputed = computed(() => (
  (overviewRef.value?.sources || []).filter(source => source.multispectral_eligible)
))
const panchromaticSourcesComputed = computed(() => (
  (overviewRef.value?.sources || []).filter(source => source.panchromatic_eligible)
))
const selectedMultispectralComputed = computed<ImageryFusionSource | null>(() => (
  multispectralSourcesComputed.value.find(
    source => source.asset_code === form.multispectralAssetCode,
  ) || null
))
const selectedPanchromaticComputed = computed<ImageryFusionSource | null>(() => (
  panchromaticSourcesComputed.value.find(
    source => source.asset_code === form.panchromaticAssetCode,
  ) || null
))
const sameProductComputed = computed<boolean>(() => Boolean(
  selectedMultispectralComputed.value?.product_identity
  && selectedMultispectralComputed.value.product_identity
    === selectedPanchromaticComputed.value?.product_identity,
))

const bandOptionsComputed = computed(() => Array.from(
  { length: selectedMultispectralComputed.value?.source_band_count || 0 },
  (_, index) => ({
    value: index + 1,
    label: `波段 ${index + 1} · ${selectedMultispectralComputed.value?.band_descriptions[index] || '无描述'}`,
  }),
))

const recommendedRgb = (source: ImageryFusionSource): number[] => {
  const find = (keywords: string[]): number => {
    const index = source.band_descriptions.findIndex(description => (
      keywords.some(keyword => (description || '').toLowerCase().includes(keyword))
    ))
    return index >= 0 ? index + 1 : 0
  }
  const recommended = [find(['red', '红']), find(['green', '绿']), find(['blue', '蓝'])]
  return recommended.every(index => index > 0)
    ? recommended
    : [1, 2, 3]
}

const selectMultispectral = (assetCode: string): void => {
  form.multispectralAssetCode = assetCode
  const source = multispectralSourcesComputed.value.find(
    item => item.asset_code === assetCode,
  )
  form.multispectralBandIndexes = source ? recommendedRgb(source) : []
}

const canSubmitComputed = computed<boolean>(() => (
  canProcessComputed.value
  && Boolean(selectedMultispectralComputed.value)
  && Boolean(selectedPanchromaticComputed.value)
  && sameProductComputed.value
  && form.multispectralBandIndexes.length === 3
  && new Set(form.multispectralBandIndexes).size === 3
  && Boolean(form.jobCode.trim())
  && Boolean(form.jobName.trim())
  && form.comment.trim().length >= 10
))

const resetForm = (): void => {
  form.jobCode = ''
  form.jobName = ''
  form.multispectralAssetCode = ''
  form.panchromaticAssetCode = ''
  form.multispectralBandIndexes = []
  form.panchromaticBandIndex = 1
  form.resamplingMethod = 'cubic'
  form.minimumOverlapRatio = 0.95
  form.minimumSpectralCorrelation = 0.8
  form.minimumSpatialDetailGain = 1.05
  form.gainLimit = 4
  form.comment = ''
}

const refresh = async (): Promise<void> => {
  try {
    await fusionStore.load()
  } catch {
    return
  }
}

const submit = async (): Promise<void> => {
  if (!canSubmitComputed.value) {
    message.warning('请选择同景多光谱和全色实体，并完成波段与质量门槛配置')
    return
  }
  try {
    await fusionStore.createJob({
      job_code: form.jobCode.trim(),
      job_name: form.jobName.trim(),
      multispectral_asset_code: form.multispectralAssetCode,
      panchromatic_asset_code: form.panchromaticAssetCode,
      multispectral_band_indexes: form.multispectralBandIndexes,
      panchromatic_band_index: form.panchromaticBandIndex,
      resampling_method: form.resamplingMethod,
      minimum_overlap_ratio: form.minimumOverlapRatio,
      minimum_spectral_correlation: form.minimumSpectralCorrelation,
      minimum_spatial_detail_gain: form.minimumSpatialDetailGain,
      gain_limit: form.gainLimit,
      comment: form.comment.trim(),
    })
    message.success('全色融合实体已生成并通过光谱与空间质量门禁')
    resetForm()
  } catch {
    return
  }
}

watch(
  () => props.open,
  (open) => {
    if (open) void refresh()
  },
  { immediate: true },
)
</script>

<template>
  <a-drawer
    :open="open"
    title="多光谱与全色影像融合"
    width="min(960px, 95vw)"
    @close="emit('update:open', false)"
  >
    <a-result
      v-if="!loadingRef && !canProcessComputed"
      status="403"
      title="当前项目身份无影像处理权限"
    />
    <a-spin v-else :spinning="loadingRef || creatingRef">
      <div class="fusion-toolbar">
        <a-alert
          type="info"
          show-icon
          message="融合不是普通重采样"
          description="平台要求同景、已定标的多光谱与更高分辨率单波段全色实体，使用分块直方图匹配 Brovey 算法输出全色网格 GeoTIFF，并计算有效重叠率、逐波段光谱相关系数和空间细节增益。"
        />
        <a-button :loading="loadingRef" @click="refresh">
          <ReloadOutlined /> 刷新来源
        </a-button>
      </div>

      <a-alert
        v-if="!panchromaticSourcesComputed.length"
        class="blocker-alert"
        type="warning"
        show-icon
        message="缺少可用全色实体"
        description="当前没有 operational、单波段、已定标且带同景产品身份的高分辨率全色影像。不会使用 Sentinel 灰度派生图或普通上采样冒充全色来源。"
      />

      <section class="fusion-section">
        <header><span><small>VERIFIED INPUTS</small><strong>同景融合输入</strong></span></header>
        <div class="form-grid">
          <label>
            <span>多光谱实体</span>
            <a-select
              :value="form.multispectralAssetCode"
              :options="multispectralSourcesComputed.map(source => ({
                value: source.asset_code,
                label: `${source.asset_name} · ${source.source_band_count} 波段 · ${source.resolution_x}m`,
              }))"
              placeholder="选择已定标多光谱影像"
              @change="selectMultispectral"
            />
          </label>
          <label>
            <span>全色实体</span>
            <a-select
              v-model:value="form.panchromaticAssetCode"
              :options="panchromaticSourcesComputed.map(source => ({
                value: source.asset_code,
                label: `${source.asset_name} · ${source.resolution_x}m`,
              }))"
              placeholder="选择同景高分辨率全色影像"
            />
          </label>
          <label class="wide">
            <span>RGB 多光谱波段</span>
            <a-select
              v-model:value="form.multispectralBandIndexes"
              mode="multiple"
              :max-count="3"
              :options="bandOptionsComputed"
              placeholder="选择三个不同波段"
            />
          </label>
        </div>
        <a-alert
          v-if="selectedMultispectralComputed && selectedPanchromaticComputed && !sameProductComputed"
          type="error"
          show-icon
          message="两个来源不是同一产品"
          description="服务端要求 SOURCE_PRODUCT_URI、STAC Item 或 Landsat 产品编号完全一致。"
        />
      </section>

      <section class="fusion-section">
        <header><span><small>QUALITY GATES</small><strong>融合算法与验收门槛</strong></span></header>
        <div class="form-grid three-columns">
          <label><span>任务编号</span><a-input v-model:value="form.jobCode" placeholder="例如 FUSION-2026-001" /></label>
          <label><span>任务名称</span><a-input v-model:value="form.jobName" placeholder="填写真实融合任务名称" /></label>
          <label><span>重采样</span><a-select v-model:value="form.resamplingMethod" :options="[{value:'cubic',label:'三次卷积'},{value:'bilinear',label:'双线性'}]" /></label>
          <label><span>最小有效重叠率</span><a-input-number
            v-model:value="form.minimumOverlapRatio"
            :min="0.1"
            :max="1"
            :step="0.01"
          /></label>
          <label><span>最低光谱相关系数</span><a-input-number
            v-model:value="form.minimumSpectralCorrelation"
            :min="0"
            :max="1"
            :step="0.01"
          /></label>
          <label><span>最小空间细节增益</span><a-input-number
            v-model:value="form.minimumSpatialDetailGain"
            :min="0.1"
            :max="10"
            :step="0.05"
          /></label>
          <label><span>Brovey 增益裁剪</span><a-input-number
            v-model:value="form.gainLimit"
            :min="1.1"
            :max="10"
            :step="0.1"
          /></label>
          <label class="wide"><span>生产依据</span><a-textarea v-model:value="form.comment" :rows="3" placeholder="说明产品来源、定标证据、融合用途和验收安排" /></label>
        </div>
        <div class="submit-row">
          <span>输出像元上限 {{ overviewRef?.max_output_pixels.toLocaleString() || '--' }}</span>
          <a-button
            type="primary"
            :disabled="!canSubmitComputed"
            :loading="creatingRef"
            @click="submit"
          >
            执行实体融合
          </a-button>
        </div>
      </section>

      <section class="fusion-section">
        <header><span><small>PHYSICAL RESULTS</small><strong>历史融合成果</strong></span><a-tag>{{ overviewRef?.jobs.length || 0 }} 个</a-tag></header>
        <a-empty v-if="!overviewRef?.jobs.length" description="尚无通过实体质量门禁的融合成果" />
        <article v-for="job in overviewRef?.jobs || []" :key="job.job_code" class="fusion-result">
          <header><span><strong>{{ job.job_name }}</strong><small>{{ job.job_code }} · {{ job.algorithm_version }}</small></span><a-tag :color="job.artifact_verified ? 'green' : 'red'">{{ job.artifact_verified ? '实体有效' : '实体失效' }}</a-tag></header>
          <div class="metric-grid">
            <span>重叠率 <b>{{ (job.overlap_ratio * 100).toFixed(2) }}%</b></span>
            <span>最低光谱相关 <b>{{ job.minimum_spectral_correlation.toFixed(4) }}</b></span>
            <span>空间细节增益 <b>{{ job.spatial_detail_gain.toFixed(4) }}</b></span>
            <span>输出分辨率 <b>{{ job.output_resolution_x }}m</b></span>
          </div>
          <p>SHA-256 {{ job.checksum_sha256 }} · {{ job.file_size_bytes.toLocaleString() }} bytes</p>
          <a-button
            size="small"
            :disabled="!job.artifact_verified"
            :loading="downloadingJobCodeRef === job.job_code"
            @click="fusionStore.downloadJob(job.job_code, job.original_filename)"
          >
            <DownloadOutlined /> 下载 GeoTIFF
          </a-button>
        </article>
      </section>
    </a-spin>
  </a-drawer>
</template>

<style scoped>
.fusion-toolbar { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; align-items: start; }
.blocker-alert { margin-top: 12px; }
.fusion-section { padding: 14px 0; border-bottom: 1px solid #e5eae7; }
.fusion-section > header, .fusion-result > header, .submit-row { display: flex; align-items: center; justify-content: space-between; }
.fusion-section > header span, .fusion-result > header span { display: flex; flex-direction: column; }
.fusion-section small, .fusion-result small { font-size: 9px; color: #849189; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 10px; }
.form-grid.three-columns { grid-template-columns: repeat(3, 1fr); }
.form-grid label { display: flex; gap: 5px; flex-direction: column; font-size: 10px; color: #52645a; }
.form-grid label.wide { grid-column: 1 / -1; }
.form-grid :deep(.ant-input-number), .form-grid :deep(.ant-select) { width: 100%; }
.submit-row { margin-top: 12px; font-size: 10px; color: #77847d; }
.fusion-result { padding: 12px; margin-top: 10px; background: #f6f9f7; border: 1px solid #e0e7e3; border-radius: 7px; }
.metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 7px; margin: 10px 0; }
.metric-grid span { padding: 8px; font-size: 9px; color: #6c7972; background: #fff; border-radius: 5px; }
.metric-grid b { display: block; color: #347957; }
.fusion-result p { font-size: 9px; color: #7c8982; word-break: break-all; }
</style>
