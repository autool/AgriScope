<script setup lang="ts">
import {
  CheckCircleOutlined,
  ClusterOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, watch } from 'vue'

import { useImageryProcessingBatchStore } from '@/store/imageryProcessingBatchStore'
import { useLayerStore } from '@/store/layerStore'
import type { ImageryProcessingBatchStepCode } from '@/types/imageryProcessingBatch'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  success: [message: string]
}>()

const batchStore = useImageryProcessingBatchStore()
const layerStore = useLayerStore()
const {
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
} = storeToRefs(batchStore)

const stepOptions = [
  { value: 'radiometric', label: '辐射定标', description: '比例系数与加性偏移' },
  { value: 'atmospheric', label: '大气校正', description: 'DOS1 暗目标扣除' },
  { value: 'geometric', label: '几何校正', description: '统一坐标系重投影' },
  { value: 'clip', label: '行政区裁剪', description: '数据库真实省/市/县边界' },
  { value: 'enhancement', label: '影像增强', description: '百分位拉伸或直方图均衡化' },
  { value: 'band_products', label: '波段与指数', description: '真彩色、假彩色与 NDVI' },
] satisfies Array<{
  value: ImageryProcessingBatchStepCode
  label: string
  description: string
}>

const stepDescriptionComputed = computed<string>(() => (
  stepOptions.find(option => option.value === stepCodeRef.value)?.description || ''
))
const boundaryOptionsComputed = computed(() => (
  layerStore.boundaryFeaturesRef.features.map(feature => ({
    value: feature.properties.boundary_code,
    label: `${{
      province: '省级',
      city: '地级',
      district: '县级',
      township: '乡级',
    }[feature.properties.boundary_level]} · ${feature.properties.boundary_name}`,
  }))
))

const formatBytes = (value: number): string => {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(2)} MB`
}

const toggleAsset = (assetCode: string): void => {
  try {
    batchStore.toggleAsset(assetCode)
  } catch (error) {
    message.warning(error instanceof Error ? error.message : '无法选择当前影像')
  }
}

const changeStep = (stepCode: ImageryProcessingBatchStepCode): void => {
  batchStore.selectStep(stepCode)
}

const submit = async (): Promise<void> => {
  try {
    const response = await batchStore.executeBatch()
    emit(
      'success',
      `批次 ${response.batch_code} 已原子完成 ${response.item_count} 景${response.step_name}`,
    )
  } catch {
    // 请求拦截器和弹窗内错误态已提供安全提示。
  }
}

watch(
  () => props.open,
  (open) => {
    if (!open) return
    void batchStore.initialize().catch(() => undefined)
  },
  { immediate: true },
)
</script>

<template>
  <a-modal
    class="imagery-processing-batch-modal"
    :open="props.open"
    title="多景同步骤原子处理"
    width="1080px"
    :confirm-loading="executingRef"
    :mask-closable="!executingRef"
    :keyboard="!executingRef"
    :closable="!executingRef"
    :ok-button-props="{ disabled: !canSubmitComputed }"
    :cancel-button-props="{ disabled: executingRef }"
    :ok-text="`原子执行 ${selectedCandidatesComputed.length} 景${candidateRowsComputed.find(item => item.targetStep)?.targetStep?.step_name || ''}`"
    cancel-text="关闭"
    @ok="submit"
    @cancel="emit('update:open', false)"
  >
    <a-alert
      type="warning"
      show-icon
      message="全部成员成功后才写入步骤状态"
      description="服务端会按资产编号稳定锁定 1–10 景业务影像及其完整流水线，重新校验上游实体、大小与 SHA-256，再生成每景独立 GeoTIFF。任一景、参数、数据库提交失败时，本批新产物和步骤状态全部回滚；已有步骤不会被批量重跑。"
    />

    <section class="batch-config">
      <label>
        <span>同步处理步骤</span>
        <a-select
          :value="stepCodeRef"
          :options="stepOptions"
          :disabled="executingRef"
          @change="changeStep"
        />
        <small>{{ stepDescriptionComputed }}</small>
      </label>
      <a-tag :color="canProcessComputed ? 'green' : 'red'">
        {{ canProcessComputed ? '具备影像处理权限' : '当前身份无处理权限' }}
      </a-tag>
    </section>

    <section class="parameter-panel">
      <template v-if="stepCodeRef === 'radiometric'">
        <label><span>比例系数</span><a-input-number v-model:value="parametersRef.scaleFactor" :min="0.000000000001" :max="10" /></label>
        <label><span>加性偏移</span><a-input-number v-model:value="parametersRef.addOffset" :min="-1000" :max="1000" /></label>
      </template>
      <template v-else-if="stepCodeRef === 'atmospheric'">
        <label><span>DOS1 暗目标百分位</span><a-input-number
          v-model:value="parametersRef.darkPercentile"
          :min="0"
          :max="10"
          addon-after="%"
        /></label>
      </template>
      <template v-else-if="stepCodeRef === 'geometric'">
        <a-alert
          class="wide"
          type="info"
          show-icon
          message="批处理仅执行同参数坐标系重投影；每景独立 GCP 或 RPC/DEM 正射继续使用单景工作流。"
        />
        <label><span>目标坐标系</span><a-input v-model:value="parametersRef.targetCrs" placeholder="EPSG:4490" /></label>
        <label><span>目标分辨率</span><a-input-number v-model:value="parametersRef.targetResolution" :min="0.000000000001" placeholder="留空自动计算" /></label>
        <label><span>重采样</span><a-select v-model:value="parametersRef.resampling" :options="[{ value: 'nearest', label: '最近邻' }, { value: 'bilinear', label: '双线性' }, { value: 'cubic', label: '三次卷积' }]" /></label>
      </template>
      <template v-else-if="stepCodeRef === 'clip'">
        <label class="wide"><span>真实行政区边界</span><a-select v-model:value="parametersRef.boundaryCode" show-search :options="boundaryOptionsComputed" /></label>
      </template>
      <template v-else-if="stepCodeRef === 'enhancement'">
        <label><span>增强方法</span><a-select v-model:value="parametersRef.enhancementMethod" :options="[{ value: 'percentile_stretch', label: '百分位拉伸' }, { value: 'histogram_equalization', label: '直方图均衡化' }]" /></label>
        <template v-if="parametersRef.enhancementMethod === 'percentile_stretch'">
          <label><span>下限百分位</span><a-input-number v-model:value="parametersRef.lowerPercentile" :min="0" :max="99.9" /></label>
          <label><span>上限百分位</span><a-input-number v-model:value="parametersRef.upperPercentile" :min="0.1" :max="100" /></label>
        </template>
        <label v-else><span>直方图分箱</span><a-input-number v-model:value="parametersRef.histogramBins" :min="16" :max="4096" /></label>
      </template>
      <template v-else>
        <a-alert
          class="wide"
          type="info"
          show-icon
          message="优先使用每景实体波段描述自动识别 Red/Green/Blue/NIR；下列索引仅作为缺少描述时的明确回退值。"
        />
        <label><span>红波段</span><a-input-number v-model:value="parametersRef.redBand" :min="1" /></label>
        <label><span>绿波段</span><a-input-number v-model:value="parametersRef.greenBand" :min="1" /></label>
        <label><span>蓝波段</span><a-input-number v-model:value="parametersRef.blueBand" :min="1" /></label>
        <label><span>近红外波段</span><a-input-number v-model:value="parametersRef.nirBand" :min="1" /></label>
      </template>
    </section>

    <section class="candidate-section">
      <header>
        <span><small>ATOMIC BATCH CANDIDATES</small><strong>真实业务影像与前置门禁</strong></span>
        <em>{{ eligibleCandidatesComputed.length }} 景可执行 · 最多 {{ batchStore.maxBatchItems }} 景</em>
      </header>
      <a-spin :spinning="loadingRef">
        <a-empty
          v-if="!loadingRef && !candidateRowsComputed.length"
          :image="null"
          description="当前项目没有可读取的影像资产"
        />
        <div v-else class="candidate-list">
          <article
            v-for="candidate in candidateRowsComputed"
            :key="candidate.asset.asset_code"
            :class="{
              selected: selectedAssetCodesRef.includes(candidate.asset.asset_code),
              blocked: !candidate.eligible,
            }"
            @click="candidate.eligible && toggleAsset(candidate.asset.asset_code)"
          >
            <input
              type="checkbox"
              :checked="selectedAssetCodesRef.includes(candidate.asset.asset_code)"
              :disabled="!candidate.eligible"
              @click.stop="toggleAsset(candidate.asset.asset_code)"
            >
            <span>
              <strong>{{ candidate.asset.asset_name }}</strong>
              <small>{{ candidate.asset.asset_code }} · {{ candidate.asset.acquired_at.slice(0, 10) }} · {{ candidate.asset.sensor_type }}</small>
            </span>
            <div>
              <a-tag :color="candidate.eligible ? 'green' : 'default'">
                {{ candidate.eligible ? '前置实体有效' : '当前不可执行' }}
              </a-tag>
              <small>{{ candidate.blocker || `${candidate.targetStep?.step_name}待处理 · ${candidate.asset.band_count || 0} 波段` }}</small>
            </div>
          </article>
        </div>
      </a-spin>
    </section>

    <section class="evidence-section">
      <label>
        <span>批次处理依据</span>
        <a-textarea
          v-model:value="commentRef"
          :rows="3"
          :maxlength="500"
          :disabled="executingRef"
          placeholder="至少 10 个字符，说明统一参数、数据来源和本批处理用途"
        />
      </label>
      <small>
        已选择 {{ selectedCandidatesComputed.length }}/{{ batchStore.maxBatchItems }} 景；
        将生成 {{ selectedCandidatesComputed.length }} 个独立实体产物、逐景审核事件和一个批次事件。
      </small>
    </section>

    <a-alert
      v-if="errorRef"
      type="error"
      show-icon
      :message="errorRef"
    />
    <a-alert
      v-else-if="validationMessagesComputed.length && selectedCandidatesComputed.length"
      type="info"
      show-icon
      :message="validationMessagesComputed[0]"
    />

    <a-alert
      v-if="lastResultRef"
      type="success"
      show-icon
      :message="`批次 ${lastResultRef.batch_code} 已原子完成 ${lastResultRef.item_count} 景${lastResultRef.step_name}`"
      :description="`${lastResultRef.processor_name} ${lastResultRef.processor_version} · 操作人 ${lastResultRef.executed_by}`"
    >
      <template #icon><CheckCircleOutlined /></template>
    </a-alert>
    <div v-if="lastResultRef" class="result-ledger">
      <span v-for="item in lastResultRef.items" :key="item.asset_code">
        <ClusterOutlined />
        <strong>{{ item.asset_code }}</strong>
        <small>{{ item.output_width }}×{{ item.output_height }} · {{ item.output_band_count }} 波段 · {{ formatBytes(item.output_file_size_bytes) }}</small>
        <small>SHA-256 {{ item.output_checksum_sha256 }}</small>
      </span>
    </div>
  </a-modal>
</template>

<style scoped>
.batch-config, .candidate-section, .evidence-section { display: grid; gap: 10px; margin-top: 14px; }
.batch-config { grid-template-columns: minmax(280px, 1fr) auto; align-items: end; }
.batch-config label, .parameter-panel label, .evidence-section label { display: grid; gap: 5px; }
.batch-config label > span, .parameter-panel label > span, .evidence-section label > span { font-size: 10px; color: #596b61; }
.batch-config small, .candidate-section small, .evidence-section small, .result-ledger small { font-size: 9px; color: #78857e; }
.parameter-panel { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; padding: 12px; margin-top: 12px; background: #f7f9f8; border: 1px solid #e0e7e3; border-radius: 6px; }
.parameter-panel .wide { grid-column: 1 / -1; }
.candidate-section > header { display: flex; align-items: center; justify-content: space-between; }
.candidate-section > header > span { display: flex; flex-direction: column; }
.candidate-section > header strong, .result-ledger strong { font-size: 11px; color: #2c4e3b; }
.candidate-section > header em { font-size: 10px; font-style: normal; color: #65756c; }
.candidate-list { display: grid; max-height: 320px; gap: 7px; overflow: auto; }
.candidate-list article { display: grid; grid-template-columns: 18px minmax(0, 1fr) minmax(190px, auto); gap: 10px; align-items: center; padding: 10px; cursor: pointer; background: #fafcfb; border: 1px solid #e1e7e4; border-radius: 6px; }
.candidate-list article.selected { background: #eef7f1; border-color: #599572; }
.candidate-list article.blocked { cursor: not-allowed; opacity: 0.62; }
.candidate-list article > span, .candidate-list article > div { display: flex; flex-direction: column; }
.candidate-list article > div { align-items: flex-end; text-align: right; }
.candidate-list article > span strong { font-size: 11px; color: #2c4e3b; }
.evidence-section { padding: 12px; background: #f7f9f8; border: 1px solid #e0e7e3; border-radius: 6px; }
.result-ledger { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; margin-top: 10px; }
.result-ledger > span { display: grid; grid-template-columns: 18px minmax(0, 1fr); gap: 3px 7px; padding: 8px; background: #eef7f1; border: 1px solid #d4e7da; border-radius: 5px; }
.result-ledger small { grid-column: 2; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 760px) {
  .batch-config, .parameter-panel, .result-ledger { grid-template-columns: 1fr; }
  .parameter-panel .wide { grid-column: 1; }
  .candidate-list article { grid-template-columns: 18px minmax(0, 1fr); }
  .candidate-list article > div { grid-column: 2; align-items: flex-start; text-align: left; }
}
</style>
