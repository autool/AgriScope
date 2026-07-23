<script setup lang="ts">
import { DownloadOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { Empty, message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { ref, watch } from 'vue'

import GrowthMonitoringCreateModal from '@/components/growth/GrowthMonitoringCreateModal.vue'
import { useGrowthMonitoringStore } from '@/store/growthMonitoringStore'
import { useMapStore } from '@/store/mapStore'
import { useUserStore } from '@/store/userStore'
import type {
  GrowthArtifactType,
  GrowthMonitoringCreatePayload,
  GrowthMonitoringRun,
} from '@/types/growthMonitoring'

const growthStore = useGrowthMonitoringStore()
const mapStore = useMapStore()
const userStore = useUserStore()
const {
  canDownloadComputed,
  canGenerateComputed,
  downloadingArtifactRef,
  eligibleSourcesComputed,
  generatingRef,
  loadingRef,
  overviewRef,
  selectedRunCodeRef,
  selectedRunComputed,
} = storeToRefs(growthStore)
const createModalOpenRef = ref<boolean>(false)

const formatPercent = (ratio: number): string => {
  const percent = ratio * 100
  if (percent < 0.1) return `${percent.toFixed(4)}%`
  if (percent < 1) return `${percent.toFixed(2)}%`
  return `${percent.toFixed(1)}%`
}

const generate = async (
  payload: Omit<GrowthMonitoringCreatePayload, 'operator_code'>,
): Promise<void> => {
  try {
    const run = await growthStore.generate(payload)
    createModalOpenRef.value = false
    message.success(`长势监测 ${run.run_code} 已生成两类物理成果`)
  } catch {
    // 请求拦截器已展示后端安全错误，保留参数便于修正。
  }
}

const selectRun = async (runCode: string): Promise<void> => {
  try {
    await growthStore.selectRun(runCode)
  } catch {
    // 保留当前任务和图层。
  }
}

const download = async (
  run: GrowthMonitoringRun,
  artifact: GrowthArtifactType,
): Promise<void> => {
  try {
    const { blob, filename } = await growthStore.download(run, artifact)
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    window.URL.revokeObjectURL(url)
  } catch {
    // 请求拦截器已展示安全错误。
  }
}

const focusSelected = (): void => {
  const bounds = selectedRunComputed.value?.bounds_wgs84
  if (!bounds || bounds.length !== 4) return
  const [west, south, east, north] = bounds
  if ([west, south, east, north].some((value) => value === undefined)) return
  mapStore.focusExtent([west, south, east, north] as [number, number, number, number])
}

watch(
  () => userStore.currentUserComputed?.user_code,
  (userCode) => {
    if (!userCode) return
    void growthStore.load()
  },
  { immediate: true },
)
</script>

<template>
  <section class="panel">
    <header>
      <span><small>MULTI-TEMPORAL NDVI</small><strong>作物长势分级</strong></span>
      <div>
        <a-button
          v-if="canGenerateComputed"
          size="small"
          type="primary"
          :disabled="eligibleSourcesComputed.length < 2"
          @click="createModalOpenRef = true"
        >
          <PlusOutlined />生成
        </a-button>
        <a-button size="small" :loading="loadingRef" @click="growthStore.load()">刷新</a-button>
      </div>
    </header>

    <a-alert
      v-if="eligibleSourcesComputed.length < 2"
      type="warning"
      show-icon
      message="至少需要两期可验证 NDVI 产品"
      description="请先在影像预处理模块为两个不同采集时相完成 band_products，并确保来源为 operational 实体。"
    />

    <div v-if="selectedRunComputed" class="metrics">
      <div><strong>{{ selectedRunComputed.anomaly_zone_count }}</strong><small>转差异常区</small></div>
      <div><strong>{{ selectedRunComputed.anomaly_area_ha.toFixed(2) }}</strong><small>异常公顷</small></div>
      <div><strong>{{ formatPercent(selectedRunComputed.spatial_coverage_ratio) }}</strong><small>任务空间覆盖</small></div>
      <div><strong>{{ formatPercent(selectedRunComputed.valid_pixel_ratio) }}</strong><small>共同范围有效像元</small></div>
    </div>

    <a-alert
      v-if="selectedRunComputed?.stale_reason"
      type="warning"
      show-icon
      message="该长势成果对应历史任务快照"
      :description="selectedRunComputed.stale_reason"
    />
    <a-alert
      v-else-if="selectedRunComputed?.source_error"
      type="error"
      show-icon
      message="长势来源实体已变化"
      :description="selectedRunComputed.source_error"
    />
    <a-alert
      v-else-if="selectedRunComputed?.artifact_error"
      type="error"
      show-icon
      message="长势成果实体校验失败"
      :description="selectedRunComputed.artifact_error"
    />

    <div class="run-list">
      <button
        v-for="run in overviewRef?.runs || []"
        :key="run.run_code"
        :class="{ active: run.run_code === selectedRunCodeRef }"
        @click="selectRun(run.run_code)"
      >
        <span>
          <strong>{{ run.run_name }}</strong>
          <small>{{ run.baseline_acquired_at.slice(0, 10) }} → {{ run.current_acquired_at.slice(0, 10) }}</small>
          <em>{{ run.run_code }} · {{ run.anomaly_zone_count }} 区 · {{ run.anomaly_area_ha.toFixed(2) }} ha</em>
        </span>
        <a-tag :color="run.task_snapshot_current ? 'green' : 'orange'">
          {{ run.task_snapshot_current ? '当前' : '历史' }}
        </a-tag>
      </button>
      <a-empty
        v-if="!loadingRef && !(overviewRef?.runs.length)"
        :image="Empty.PRESENTED_IMAGE_SIMPLE"
        description="尚未生成真实多时相 NDVI 长势成果"
      />
    </div>

    <section v-if="selectedRunComputed" class="detail-card">
      <h3>{{ selectedRunComputed.run_code }}</h3>
      <dl>
        <div><dt>基准期</dt><dd>{{ selectedRunComputed.baseline_asset_name }}</dd></div>
        <div><dt>监测期</dt><dd>{{ selectedRunComputed.current_asset_name }}</dd></div>
        <div><dt>任务耕地</dt><dd>{{ selectedRunComputed.task_plot_count }} 个图斑</dd></div>
        <div><dt>完整面积</dt><dd>{{ selectedRunComputed.task_farmland_area_ha.toFixed(2) }} ha</dd></div>
        <div><dt>共同覆盖</dt><dd>{{ selectedRunComputed.common_footprint_farmland_area_ha.toFixed(2) }} ha / {{ formatPercent(selectedRunComputed.spatial_coverage_ratio) }}</dd></div>
        <div><dt>有效像元</dt><dd>{{ selectedRunComputed.valid_pixel_count }} / {{ selectedRunComputed.common_footprint_mask_pixel_count }}（{{ formatPercent(selectedRunComputed.valid_pixel_ratio) }}）</dd></div>
        <div><dt>分级阈值</dt><dd>差 ≤ {{ selectedRunComputed.poor_delta_threshold }} / 好 ≥ {{ selectedRunComputed.good_delta_threshold }}</dd></div>
        <div><dt>处理器</dt><dd>{{ selectedRunComputed.algorithm_version }}</dd></div>
        <div><dt>生成人</dt><dd>{{ selectedRunComputed.created_by }} · {{ selectedRunComputed.created_by_role }}</dd></div>
      </dl>
      <div class="class-share">
        <span class="poor"><i :style="{ flexGrow: selectedRunComputed.poor_pixel_count }" />差 {{ selectedRunComputed.poor_pixel_count }}</span>
        <span class="normal"><i :style="{ flexGrow: selectedRunComputed.normal_pixel_count }" />正常 {{ selectedRunComputed.normal_pixel_count }}</span>
        <span class="good"><i :style="{ flexGrow: selectedRunComputed.good_pixel_count }" />好 {{ selectedRunComputed.good_pixel_count }}</span>
      </div>
      <div class="downloads">
        <a-button
          size="small"
          :disabled="selectedRunComputed.bounds_wgs84.length !== 4"
          @click="focusSelected"
        >
          定位监测范围
        </a-button>
        <a-button
          size="small"
          :disabled="!canDownloadComputed || !selectedRunComputed.classification_verified"
          :loading="downloadingArtifactRef === `${selectedRunComputed.run_code}:classification`"
          @click="download(selectedRunComputed, 'classification')"
        >
          <DownloadOutlined />分级 GeoTIFF
        </a-button>
        <a-button
          size="small"
          :disabled="!canDownloadComputed || !selectedRunComputed.anomaly_verified"
          :loading="downloadingArtifactRef === `${selectedRunComputed.run_code}:anomalies`"
          @click="download(selectedRunComputed, 'anomalies')"
        >
          <DownloadOutlined />异常区 GeoJSON
        </a-button>
      </div>
      <code>分类 SHA-256 {{ selectedRunComputed.classification_sha256 }}</code>
      <code>异常区 SHA-256 {{ selectedRunComputed.anomaly_sha256 }}</code>
    </section>

    <GrowthMonitoringCreateModal
      :open="createModalOpenRef"
      :loading="generatingRef"
      :sources="eligibleSourcesComputed"
      :max-output-pixels="overviewRef?.max_output_pixels || 0"
      @cancel="createModalOpenRef = false"
      @submit="generate"
    />
  </section>
</template>

<style scoped>
.panel { height: 100%; padding: 12px; overflow: auto; }
header { display: flex; align-items: center; justify-content: space-between; }
header > span { display: flex; flex-direction: column; }
header > div { display: flex; gap: 5px; }
header small, .run-list small, .run-list em { font-size: 8px; color: #849088; }
header strong { font-size: 12px; }
.metrics { display: grid; grid-template-columns: repeat(2, 1fr); gap: 5px; margin: 10px 0; }
.metrics div { padding: 8px; text-align: center; background: #f6f7f6; border-radius: 5px; }
.metrics strong, .metrics small { display: block; }
.metrics strong { font-size: 15px; color: #a42e43; }
.run-list { margin-top: 9px; }
.run-list button { display: flex; justify-content: space-between; width: 100%; padding: 8px; text-align: left; background: #fff; border: 0; border-bottom: 1px solid #edf0ee; }
.run-list button.active { background: #fff4f5; border-left: 3px solid #b92139; }
.run-list span { display: grid; min-width: 0; }
.run-list strong { font-size: 10px; }
.run-list em { font-style: normal; }
.detail-card { padding: 10px; margin-top: 10px; background: #f8faf8; border: 1px solid #e0e6e2; border-radius: 6px; }
.detail-card h3 { margin: 0 0 7px; font-size: 11px; }
dl { display: grid; gap: 4px; margin: 0; }
dl div { display: grid; grid-template-columns: 58px minmax(0, 1fr); gap: 6px; font-size: 8px; }
dt { color: #839087; } dd { margin: 0; color: #3f5148; }
.class-share { display: grid; grid-template-columns: repeat(3, 1fr); gap: 5px; margin: 9px 0; }
.class-share span { display: grid; gap: 3px; font-size: 8px; }
.class-share i { height: 5px; border-radius: 3px; }
.class-share .poor i { background: #c43e49; } .class-share .normal i { background: #e5ad43; } .class-share .good i { background: #3e975b; }
.downloads { display: flex; gap: 6px; }
code { display: block; margin-top: 5px; overflow: hidden; font-size: 7px; color: #68766e; text-overflow: ellipsis; white-space: nowrap; }
</style>
