<script setup lang="ts">
import {
  CheckCircleOutlined,
  CloudUploadOutlined,
  PlayCircleOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref } from 'vue'

import ImageryStepActionModal from '@/components/imagery/ImageryStepActionModal.vue'
import { useAssetStore } from '@/store/assetStore'
import { useImageryStore } from '@/store/imageryStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type { ImageryAssetItem, ImageryProcessingStep } from '@/types/workbench'
import type { ImageryQuicklookProduct, ImageryQuicklookProductCode } from '@/types/workbench'

const imageryStore = useImageryStore()
const assetStore = useAssetStore()
const workbenchStore = useWorkbenchStore()
const {
  canProcessComputed,
  loadingRef,
  processingRef,
  processingStepCodeRef,
  quicklookRef,
} = storeToRefs(imageryStore)
const { catalogRef } = storeToRefs(assetStore)
const actionVisibleRef = ref<boolean>(false)
const actionModeRef = ref<'execute' | 'register' | 'source-accept'>('execute')
const selectedStepRef = ref<ImageryProcessingStep | null>(null)
const selectedAssetCodeRef = ref<string>('')
const selectedAssetComputed = computed<ImageryAssetItem | null>(() => (
  catalogRef.value?.items.find(
    (item) => item.asset_code === selectedAssetCodeRef.value,
  ) || null
))
const quicklookProduct = (
  productCode: ImageryQuicklookProductCode,
): ImageryQuicklookProduct | null => (
  quicklookRef.value?.products.find(
    (product) => product.product_code === productCode,
  ) || null
)
const sourceQuicklookComputed = computed(() => quicklookProduct('source'))
const trueColorQuicklookComputed = computed(() => quicklookProduct('true_color'))
const falseColorQuicklookComputed = computed(() => quicklookProduct('false_color'))
const ndviQuicklookComputed = computed(() => quicklookProduct('ndvi'))

const quicklookStyle = (
  product: ImageryQuicklookProduct | null,
): Record<string, string> => (
  product?.available && product.preview_url
    ? { backgroundImage: `url("${product.preview_url}")` }
    : {}
)

const statusColor = (step: ImageryProcessingStep): string => {
  if (step.output_verified) return 'green'
  if (step.status === 'artifact_missing') return 'error'
  if (step.status === 'running') return 'processing'
  return 'default'
}

const statusLabel = (step: ImageryProcessingStep): string => {
  const evidence = step.parameters.artifact_evidence
  if (
    typeof evidence === 'object'
    && evidence !== null
    && 'execution_mode' in evidence
    && evidence.execution_mode === 'source_level_acceptance'
  ) return '源级已承认'
  if (step.output_verified) return '产物已校验'
  if (step.status === 'artifact_missing') return '产物缺失'
  if (step.status === 'running') return '处理中'
  return '待登记'
}

const stepBlocked = (step: ImageryProcessingStep): boolean => (
  (processingRef.value?.steps || []).some(
    (candidate) => candidate.sequence < step.sequence && !candidate.output_verified,
  )
)

const sourceAcceptanceAvailable = (step: ImageryProcessingStep): boolean => (
  processingRef.value?.processing_level?.toUpperCase() === 'L2A'
  && ['radiometric', 'atmospheric'].includes(step.step_code)
)

const sourceAccepted = (step: ImageryProcessingStep): boolean => {
  const evidence = step.parameters.artifact_evidence
  return (
    typeof evidence === 'object'
    && evidence !== null
    && 'execution_mode' in evidence
    && evidence.execution_mode === 'source_level_acceptance'
  )
}

const openActionModal = (
  step: ImageryProcessingStep,
  mode: 'execute' | 'register' | 'source-accept',
): void => {
  selectedStepRef.value = step
  actionModeRef.value = mode
  actionVisibleRef.value = true
}

/**
 * 切换当前查看和处理的影像资产。
 * Args:
 *   assetCode: 影像资产编号。
 * Returns:
 *   Promise<void>: 对应处理流水线加载完成后结束。
 */
const selectAsset = async (assetCode: string): Promise<void> => {
  selectedAssetCodeRef.value = assetCode
  try {
    await imageryStore.load(assetCode)
  } catch {
    // 请求拦截器已显示安全错误，保留当前资产选择以便重试。
  }
}

const handleActionSuccess = (successMessage: string): void => {
  message.success(successMessage)
}

onMounted(() => {
  void (async () => {
    // 子路由会早于布局父组件触发 mounted。这里显式同步总览和目录，
    // 避免总览尚未就绪时按采集日期误选更新但仅用于联调的演示资产。
    await Promise.all([
      assetStore.load(),
      workbenchStore.refreshOverview(),
    ])
    const overviewAssetCode = workbenchStore.overviewRef?.imagery?.asset_code
    const preferredAsset = catalogRef.value?.items.find(
      (item) => item.asset_code === overviewAssetCode && item.file_verified,
    ) || catalogRef.value?.items.find(
      (item) => (
        item.data_status === 'operational'
        && item.file_verified
        && (item.band_count || 0) >= 4
      ),
    ) || catalogRef.value?.items.find(
      (item) => item.data_status === 'operational' && item.file_verified,
    ) || catalogRef.value?.items.find(
      (item) => item.file_verified && (item.band_count || 0) >= 4,
    ) || catalogRef.value?.items[0]
    if (preferredAsset) await selectAsset(preferredAsset.asset_code)
  })()
})
</script>

<template>
  <div class="imagery-view">
    <section class="scene-workspace">
      <div
        class="scene-preview"
        :class="{ unavailable: !sourceQuicklookComputed?.available }"
        :style="quicklookStyle(sourceQuicklookComputed)"
      >
        <div class="scene-title">
          <span><small>PHYSICAL RASTER QUICKLOOK</small><strong>实体源影像快视图</strong></span>
          <a-tag :color="quicklookRef?.data_status === 'demo' ? 'orange' : 'green'">
            {{ quicklookRef?.data_status === 'demo' ? '明确演示数据' : '业务实体文件' }}
          </a-tag>
        </div>
        <div class="scene-meta">
          <template v-if="sourceQuicklookComputed?.available">
            {{ processingRef?.asset_code }} · 波段 {{ sourceQuicklookComputed.band_indexes.join('/') }} ·
            SHA256 {{ sourceQuicklookComputed.source_checksum_sha256?.slice(0, 12) }}…
          </template>
          <template v-else>
            {{ sourceQuicklookComputed?.unavailable_reason || '尚未选择可读取的实体影像资产' }}
          </template>
        </div>
      </div>
      <div class="product-grid">
        <article
          class="true-color"
          :class="{ unavailable: !trueColorQuicklookComputed?.available }"
          :style="quicklookStyle(trueColorQuicklookComputed)"
        >
          <span><strong>真彩色产品</strong><small>{{ trueColorQuicklookComputed?.available ? `波段 ${trueColorQuicklookComputed.band_indexes.join('/')}` : trueColorQuicklookComputed?.unavailable_reason || '未生成' }}</small></span>
          <a-tag :color="trueColorQuicklookComputed?.available ? 'green' : 'default'">{{ trueColorQuicklookComputed?.available ? '实体产物快视图' : '不可用' }}</a-tag>
        </article>
        <article
          class="false-color"
          :class="{ unavailable: !falseColorQuicklookComputed?.available }"
          :style="quicklookStyle(falseColorQuicklookComputed)"
        >
          <span><strong>标准假彩色</strong><small>{{ falseColorQuicklookComputed?.available ? `波段 ${falseColorQuicklookComputed.band_indexes.join('/')}` : falseColorQuicklookComputed?.unavailable_reason || '未生成' }}</small></span>
          <a-tag :color="falseColorQuicklookComputed?.available ? 'green' : 'default'">{{ falseColorQuicklookComputed?.available ? '实体产物快视图' : '不可用' }}</a-tag>
        </article>
        <article
          class="ndvi"
          :class="{ unavailable: !ndviQuicklookComputed?.available }"
          :style="quicklookStyle(ndviQuicklookComputed)"
        >
          <span><strong>NDVI 植被指数</strong><small>{{ ndviQuicklookComputed?.available && ndviQuicklookComputed.value_range ? `${ndviQuicklookComputed.value_range[0].toFixed(3)} ～ ${ndviQuicklookComputed.value_range[1].toFixed(3)}` : ndviQuicklookComputed?.unavailable_reason || '未生成' }}</small></span>
          <a-tag :color="ndviQuicklookComputed?.available ? 'green' : 'default'">{{ ndviQuicklookComputed?.available ? '实体产物快视图' : '不可用' }}</a-tag>
        </article>
      </div>
    </section>

    <aside class="processing-panel">
      <header>
        <span><small>PROCESSING PIPELINE</small><strong>影像预处理流水线</strong></span>
        <b>{{ processingRef?.completion_rate ?? 0 }}%</b>
      </header>
      <a-select
        v-model:value="selectedAssetCodeRef"
        class="asset-selector"
        :loading="loadingRef"
        :options="(catalogRef?.items || []).map((item) => ({
          value: item.asset_code,
          label: `${item.asset_code} · ${item.data_status === 'demo' ? '明确演示' : '业务数据'} · ${item.file_verified ? '实体可用' : '仅元数据'}`,
        }))"
        @change="selectAsset"
      />
      <a-alert
        v-if="!catalogRef?.items.length"
        type="info"
        show-icon
        message="尚未上传影像资产"
        description="请先在数据资产页面上传 GeoTIFF、IMG 或 HDF 实体文件。"
      />
      <a-alert
        v-if="selectedAssetComputed?.data_status === 'demo'"
        type="warning"
        show-icon
        message="当前为明确演示影像"
        description="仅用于功能联调，不得作为正式遥感监测成果。"
      />
      <a-alert
        v-if="selectedAssetComputed && !selectedAssetComputed.file_verified"
        type="warning"
        show-icon
        message="当前资产缺少可用源文件，只能查看状态或登记已有外部产物。"
      />
      <template v-if="processingRef">
        <a-progress :percent="processingRef.completion_rate" :show-info="false" stroke-color="#3f8f66" />
        <div class="asset-meta">
          <div><small>传感器</small><strong>{{ processingRef.sensor_type }}</strong></div>
          <div><small>云量</small><strong>{{ processingRef.cloud_cover ?? '--' }}<template v-if="processingRef.cloud_cover !== null">%</template></strong></div>
          <div><small>采集日期</small><strong>{{ processingRef.acquired_at.slice(0, 10) }}</strong></div>
          <div><small>处理级别</small><strong>{{ processingRef.processing_level || '--' }}</strong></div>
        </div>
        <div class="step-list">
          <article v-for="step in processingRef.steps" :key="step.step_code" :class="step.status">
            <i><CheckCircleOutlined v-if="step.output_verified" /><span v-else>{{ step.sequence }}</span></i>
            <div>
              <header><span><strong>{{ step.step_name }}</strong><small>{{ step.step_code }}</small></span><a-tag :color="statusColor(step)">{{ statusLabel(step) }}</a-tag></header>
              <a-progress :percent="step.progress" :show-info="false" size="small" />
              <p>{{ step.artifact_error || step.output_uri || '尚未登记实体产物' }}</p>
              <p v-if="step.output_verified" class="artifact-evidence">
                {{ sourceAccepted(step) ? '复用已校验 L2A 源实体，未执行重复算法' : `${step.processor_name} ${step.processor_version}` }} ·
                {{ step.output_size_bytes }} bytes ·
                SHA256 {{ step.output_checksum_sha256?.slice(0, 12) }}…
              </p>
              <div v-if="!step.output_verified" class="step-actions">
                <a-button
                  v-if="sourceAcceptanceAvailable(step)"
                  size="small"
                  :loading="processingStepCodeRef === step.step_code"
                  :disabled="!canProcessComputed || !selectedAssetComputed?.file_verified || stepBlocked(step)"
                  :title="stepBlocked(step) ? '请先完成上一步处理' : '复核实体源文件标签和 SHA-256，不执行重复算法'"
                  @click="openActionModal(step, 'source-accept')"
                >
                  <SafetyCertificateOutlined /> 源级承认
                </a-button>
                <a-button
                  type="primary"
                  size="small"
                  :loading="processingStepCodeRef === step.step_code"
                  :disabled="!canProcessComputed || !selectedAssetComputed?.file_verified || stepBlocked(step)"
                  :title="stepBlocked(step) ? '请先完成上一步处理' : '由平台执行明确参数化算法'"
                  @click="openActionModal(step, 'execute')"
                >
                  <PlayCircleOutlined /> 平台执行
                </a-button>
                <a-button
                  size="small"
                  :disabled="!canProcessComputed || stepBlocked(step)"
                  @click="openActionModal(step, 'register')"
                >
                  <CloudUploadOutlined /> 登记外部产物
                </a-button>
              </div>
            </div>
          </article>
        </div>
      </template>
    </aside>

    <ImageryStepActionModal
      v-model:open="actionVisibleRef"
      :step="selectedStepRef"
      :asset-code="processingRef?.asset_code || ''"
      :asset-verified="selectedAssetComputed?.file_verified || false"
      :asset-band-count="selectedAssetComputed?.band_count || null"
      :asset-band-descriptions="selectedAssetComputed?.raster_metadata.descriptions || []"
      :processing-level="processingRef?.processing_level || null"
      :initial-mode="actionModeRef"
      @success="handleActionSuccess"
    />
  </div>
</template>

<style scoped>
.imagery-view { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 10px; height: 100%; padding: 10px; background: #18241f; }
.scene-workspace { display: grid; grid-template-rows: minmax(250px, 1fr) 140px; gap: 10px; min-width: 0; min-height: 0; }
.scene-preview { position: relative; overflow: hidden; background: #0f1915 center / contain no-repeat; border: 1px solid rgb(255 255 255 / 13%); border-radius: 8px; }
.scene-preview.unavailable { background-image: radial-gradient(circle at center, #24362e, #101914) !important; }
.scene-preview::after { position: absolute; inset: 0; content: ''; box-shadow: inset 0 0 80px rgb(0 0 0 / 25%); }
.scene-title, .scene-meta { position: absolute; z-index: 1; color: #fff; background: rgb(15 42 30 / 80%); border: 1px solid rgb(255 255 255 / 12%); border-radius: 5px; backdrop-filter: blur(6px); }
.scene-title { top: 14px; left: 14px; display: flex; gap: 20px; align-items: center; padding: 8px 10px; }
.scene-title > span { display: flex; flex-direction: column; }
.scene-title small { font-size: 7px; color: rgb(255 255 255 / 55%); }
.scene-title strong { font-size: 11px; }
.scene-meta { right: 14px; bottom: 14px; padding: 6px 9px; font-size: 8px; }
.product-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 9px; }
.product-grid article { position: relative; display: flex; align-items: end; justify-content: space-between; padding: 11px; overflow: hidden; color: #fff; background: #1c2a24 center / contain no-repeat; border: 1px solid rgb(255 255 255 / 10%); border-radius: 7px; }
.product-grid article::after { position: absolute; inset: 0; content: ''; background: linear-gradient(transparent 30%, rgb(3 19 12 / 85%)); }
.product-grid article.unavailable { background-image: linear-gradient(135deg, #2c3a34, #18241f) !important; }
.product-grid article > span, .product-grid article > :deep(.ant-tag) { position: relative; z-index: 1; }
.product-grid article > span { display: flex; flex-direction: column; }
.product-grid strong { font-size: 10px; }
.product-grid small { font-size: 8px; color: rgb(255 255 255 / 62%); }
.processing-panel { padding: 14px; overflow: auto; background: #fff; border-radius: 8px; }
.processing-panel > header { display: flex; align-items: center; justify-content: space-between; }
.processing-panel header > span { display: flex; flex-direction: column; }
.processing-panel header small { font-size: 7px; color: #8b9690; }
.processing-panel header strong { font-size: 11px; }
.processing-panel > header b { font-size: 20px; color: #347957; }
.asset-selector { width: 100%; margin: 10px 0 8px; }
.asset-meta { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin: 10px 0; }
.asset-meta > div { padding: 8px; background: #f4f7f5; border-radius: 5px; }
.asset-meta small, .asset-meta strong { display: block; }
.asset-meta small { font-size: 7px; color: #87938d; }
.asset-meta strong { margin-top: 2px; font-size: 8px; }
.step-list article { display: grid; grid-template-columns: 28px 1fr; gap: 8px; padding: 10px 0; border-bottom: 1px solid #e9ecea; }
.step-list article > i { display: grid; width: 27px; height: 27px; font-size: 9px; font-style: normal; color: #fff; background: #d8953d; border-radius: 50%; place-items: center; }
.step-list article.completed > i { background: #4a9b70; }
.step-list article.artifact_missing > i { background: #cf5656; }
.step-list article header { display: flex; align-items: center; justify-content: space-between; }
.step-list article header > span { display: flex; flex-direction: column; }
.step-list article p { margin: 2px 0 5px; overflow: hidden; font-size: 7px; color: #8b9690; text-overflow: ellipsis; white-space: nowrap; }
.step-list article .artifact-evidence { color: #397d59; }
.step-actions { display: flex; gap: 5px; flex-wrap: wrap; }
</style>
