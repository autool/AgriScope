<script setup lang="ts">
import {
  CheckCircleOutlined,
  HistoryOutlined,
  ReloadOutlined,
  WarningOutlined,
} from '@ant-design/icons-vue'
import { storeToRefs } from 'pinia'
import { computed, ref, watch } from 'vue'

import PublicImageryArchivePanel from '@/components/imagery/PublicImageryArchivePanel.vue'
import { useImageryHistoryStore } from '@/store/imageryHistoryStore'
import type {
  ImageryCoverageCell,
  ImageryHistoryAsset,
  ImageryHistoryBoundary,
  ImageryHistoryDataStatus,
  ImageryTraceEvent,
  ImageryTraceSeverity,
} from '@/types/imageryHistory'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

type AssetStatusFilter = 'all' | ImageryHistoryDataStatus

const historyStore = useImageryHistoryStore()
const { overviewRef, loadingRef, errorRef } = storeToRefs(historyStore)
const activeTabRef = ref<'coverage' | 'timeline' | 'public-archive'>('coverage')
const assetStatusFilterRef = ref<AssetStatusFilter>('operational')
const selectedPrefectureRef = ref<string>('all')

const formatDateTime = (value: string | null): string => (
  value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '--'
)

const formatDate = (value: string | null): string => (
  value ? value.slice(0, 10) : '--'
)

const displayedAssetsComputed = computed<ImageryHistoryAsset[]>(() => (
  (overviewRef.value?.assets || []).filter(asset => (
    assetStatusFilterRef.value === 'all'
    || asset.data_status === assetStatusFilterRef.value
  ))
))

const prefectureBoundariesComputed = computed<ImageryHistoryBoundary[]>(() => (
  (overviewRef.value?.boundaries || [])
    .filter(boundary => boundary.boundary_level === 'city')
    .sort((first, second) => first.boundary_code.localeCompare(second.boundary_code))
))

const prefectureNameByCodeComputed = computed<Map<string, string>>(() => new Map(
  prefectureBoundariesComputed.value.map(boundary => [
    boundary.boundary_code,
    boundary.boundary_name,
  ]),
))

const districtBoundariesComputed = computed<ImageryHistoryBoundary[]>(() => (
  (overviewRef.value?.boundaries || [])
    .filter(boundary => (
      boundary.boundary_level === 'district'
      && (
        selectedPrefectureRef.value === 'all'
        || boundary.parent_code === selectedPrefectureRef.value
      )
    ))
    .sort((first, second) => first.boundary_code.localeCompare(second.boundary_code))
))

const coverageByKeyComputed = computed<Map<string, ImageryCoverageCell>>(() => new Map(
  (overviewRef.value?.coverage_cells || []).map(cell => [
    `${cell.asset_code}|${cell.county_code}`,
    cell,
  ]),
))

const matrixStyleComputed = computed<Record<string, string>>(() => ({
  gridTemplateColumns: `190px repeat(${Math.max(displayedAssetsComputed.value.length, 1)}, minmax(165px, 1fr))`,
}))

const displayedAssetCodesComputed = computed<Set<string>>(() => new Set(
  displayedAssetsComputed.value.map(asset => asset.asset_code),
))

const displayedEventsComputed = computed<ImageryTraceEvent[]>(() => (
  (overviewRef.value?.trace_events || []).filter(event => (
    displayedAssetCodesComputed.value.has(event.asset_code)
  ))
))

const issueCountComputed = computed<number>(() => (
  displayedEventsComputed.value.filter(event => (
    event.severity === 'warning' || event.severity === 'error'
  )).length
))

const coverageCell = (
  assetCode: string,
  countyCode: string,
): ImageryCoverageCell | null => (
  coverageByKeyComputed.value.get(`${assetCode}|${countyCode}`) || null
)

const coverageLabel = (cell: ImageryCoverageCell | null): string => {
  if (!cell || cell.coverage_percent <= 0) return '—'
  if (cell.coverage_percent < 0.01) return '<0.01%'
  return `${cell.coverage_percent.toFixed(2)}%`
}

const severityColor = (severity: ImageryTraceSeverity): string => ({
  success: 'green',
  info: 'blue',
  warning: 'orange',
  error: 'red',
}[severity])

const severityLabel = (severity: ImageryTraceSeverity): string => ({
  success: '已验证',
  info: '历史证据',
  warning: '待处理',
  error: '实体失效',
}[severity])

const refresh = async (): Promise<void> => {
  try {
    await historyStore.load()
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
    title="历史影像覆盖矩阵与问题追溯"
    width="min(1180px, 96vw)"
    @close="emit('update:open', false)"
  >
    <a-spin :spinning="loadingRef">
      <div class="history-toolbar">
        <a-alert
          type="info"
          show-icon
          message="覆盖率来自真实行政区面积相交"
          description="每个单元格以数据库县界 geography 面积为分母、影像 WGS84 足迹交集为分子。处理时间线重新校验源文件和步骤实体 SHA-256；演示影像始终单独标识。"
        />
        <a-button :loading="loadingRef" @click="refresh">
          <ReloadOutlined /> 刷新证据
        </a-button>
      </div>

      <a-alert
        v-if="errorRef"
        class="state-alert"
        type="error"
        show-icon
        :message="errorRef"
      />

      <template v-else-if="overviewRef">
        <section class="history-summary">
          <article>
            <small>历史时相</small>
            <strong>{{ overviewRef.asset_count }}</strong>
            <span>{{ formatDate(overviewRef.time_start) }} 至 {{ formatDate(overviewRef.time_end) }}</span>
          </article>
          <article>
            <small>正式业务影像</small>
            <strong>{{ overviewRef.verified_operational_asset_count }}/{{ overviewRef.operational_asset_count }}</strong>
            <span>源实体与 SHA-256 复核通过</span>
          </article>
          <article>
            <small>真实行政层级</small>
            <strong>{{ overviewRef.prefecture_count }}/{{ overviewRef.county_count }}</strong>
            <span>地级区域 / 县区</span>
          </article>
          <article :class="{ warning: issueCountComputed > 0 }">
            <small>当前筛选待处理证据</small>
            <strong>{{ issueCountComputed }}</strong>
            <span>必选步骤、云量或实体异常</span>
          </article>
        </section>

        <div class="history-filters">
          <a-segmented
            v-model:value="assetStatusFilterRef"
            :options="[
              { value: 'operational', label: '正式业务影像' },
              { value: 'demo', label: '明确演示影像' },
              { value: 'all', label: '全部时相' },
            ]"
          />
          <a-select
            v-model:value="selectedPrefectureRef"
            class="prefecture-filter"
            :options="[
              { value: 'all', label: `全部 ${overviewRef.prefecture_count} 个地级区域` },
              ...prefectureBoundariesComputed.map(boundary => ({
                value: boundary.boundary_code,
                label: `${boundary.boundary_name} · ${boundary.boundary_code}`,
              })),
            ]"
          />
          <span class="source-note">
            边界来源：{{ overviewRef.boundaries[0]?.source_name || '--' }} ·
            {{ overviewRef.boundaries[0]?.source_version || '--' }}
          </span>
        </div>

        <a-tabs v-model:active-key="activeTabRef" class="history-tabs">
          <a-tab-pane key="coverage" tab="县区覆盖矩阵">
            <a-alert
              v-if="!displayedAssetsComputed.length"
              type="warning"
              show-icon
              message="当前筛选没有影像时相"
            />
            <div v-else class="coverage-matrix" :style="matrixStyleComputed">
              <div class="matrix-corner sticky-column sticky-header">
                县区 / 影像时相
              </div>
              <div
                v-for="asset in displayedAssetsComputed"
                :key="`header-${asset.asset_code}`"
                class="matrix-asset sticky-header"
              >
                <div>
                  <strong>{{ formatDate(asset.acquired_at) }}</strong>
                  <a-tag v-if="asset.is_latest_operational" color="green">当前业务时相</a-tag>
                  <a-tag v-else-if="asset.data_status === 'demo'" color="orange">明确演示</a-tag>
                </div>
                <span>{{ asset.sensor_type }} · {{ asset.resolution_m ?? '--' }}m</span>
                <span>处理 {{ asset.processing_completion_rate.toFixed(0) }}% · 问题 {{ asset.issue_count }}</span>
              </div>

              <template v-for="county in districtBoundariesComputed" :key="county.boundary_code">
                <div class="matrix-county sticky-column">
                  <strong>{{ county.boundary_name }}</strong>
                  <span>{{ prefectureNameByCodeComputed.get(county.parent_code || '') }} · {{ county.boundary_code }}</span>
                </div>
                <a-tooltip
                  v-for="asset in displayedAssetsComputed"
                  :key="`${asset.asset_code}-${county.boundary_code}`"
                  placement="top"
                >
                  <template #title>
                    <template v-if="coverageCell(asset.asset_code, county.boundary_code)">
                      覆盖 {{ coverageCell(asset.asset_code, county.boundary_code)?.covered_area_ha.toFixed(2) }} ha /
                      县区 {{ coverageCell(asset.asset_code, county.boundary_code)?.county_area_ha.toFixed(2) }} ha
                    </template>
                    <template v-else>无覆盖记录</template>
                  </template>
                  <div
                    class="matrix-cell"
                    :class="coverageCell(asset.asset_code, county.boundary_code)?.coverage_status || 'none'"
                  >
                    {{ coverageLabel(coverageCell(asset.asset_code, county.boundary_code)) }}
                  </div>
                </a-tooltip>
              </template>
            </div>
          </a-tab-pane>

          <a-tab-pane key="timeline" tab="处理与问题时间线">
            <a-empty
              v-if="!displayedEventsComputed.length"
              description="当前筛选没有处理或问题证据"
            />
            <a-timeline v-else class="trace-timeline">
              <a-timeline-item
                v-for="event in displayedEventsComputed"
                :key="event.event_code"
                :color="severityColor(event.severity)"
              >
                <article class="trace-event">
                  <header>
                    <span>
                      <CheckCircleOutlined v-if="event.severity === 'success'" />
                      <WarningOutlined v-else-if="event.severity === 'warning' || event.severity === 'error'" />
                      <HistoryOutlined v-else />
                      <strong>{{ event.title }}</strong>
                    </span>
                    <a-tag :color="severityColor(event.severity)">
                      {{ severityLabel(event.severity) }}
                    </a-tag>
                  </header>
                  <p>{{ event.asset_name }} · {{ event.asset_code }}<template v-if="event.step_code"> · {{ event.step_code }}</template></p>
                  <p>{{ event.detail }}</p>
                  <footer>
                    <time>{{ formatDateTime(event.occurred_at) }}</time>
                    <span v-if="event.evidence_sha256">SHA-256 {{ event.evidence_sha256.slice(0, 16) }}…</span>
                  </footer>
                </article>
              </a-timeline-item>
            </a-timeline>
          </a-tab-pane>
          <a-tab-pane key="public-archive" tab="公开历史语料">
            <PublicImageryArchivePanel />
          </a-tab-pane>
        </a-tabs>
      </template>
    </a-spin>
  </a-drawer>
</template>

<style scoped>
.history-toolbar { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; align-items: start; }
.state-alert { margin-top: 12px; }
.history-summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 14px 0; }
.history-summary article { display: flex; min-height: 92px; padding: 13px; flex-direction: column; background: #f5f8f6; border: 1px solid #e3e9e5; border-radius: 7px; }
.history-summary article.warning { background: #fff8ed; border-color: #f2d5a5; }
.history-summary small { font-size: 10px; color: #7c8982; }
.history-summary strong { margin: 4px 0; font-size: 24px; color: #245f43; }
.history-summary article.warning strong { color: #b56b18; }
.history-summary span { font-size: 10px; color: #65736c; }
.history-filters { display: flex; gap: 10px; align-items: center; padding: 10px; background: #f7f9f8; border: 1px solid #e5eae7; border-radius: 7px; }
.prefecture-filter { width: 260px; }
.source-note { margin-left: auto; font-size: 10px; color: #77847d; }
.history-tabs { margin-top: 8px; }
.coverage-matrix { display: grid; max-height: 560px; overflow: auto; border: 1px solid #dfe6e2; border-radius: 7px; }
.coverage-matrix > div { min-width: 0; border-right: 1px solid #e5eae7; border-bottom: 1px solid #e5eae7; }
.sticky-header { position: sticky; top: 0; z-index: 3; }
.sticky-column { position: sticky; left: 0; z-index: 2; }
.matrix-corner { z-index: 4; display: grid; padding: 12px; color: #eef7f2; background: #1d4f38; place-items: center start; }
.matrix-asset { display: flex; min-height: 76px; padding: 10px; flex-direction: column; background: #edf5f0; }
.matrix-asset div { display: flex; gap: 6px; align-items: center; }
.matrix-asset strong { font-size: 12px; color: #254d38; }
.matrix-asset span { margin-top: 4px; font-size: 9px; color: #6d7c74; }
.matrix-county { display: flex; min-height: 48px; padding: 8px 10px; flex-direction: column; justify-content: center; background: #fff; }
.matrix-county strong { font-size: 11px; color: #273b31; }
.matrix-county span { margin-top: 2px; font-size: 9px; color: #829087; }
.matrix-cell { display: grid; min-height: 48px; font-size: 10px; color: #77847d; background: #fafcfb; place-items: center; }
.matrix-cell.partial { font-weight: 600; color: #2d6f4e; background: #e2f2e8; }
.matrix-cell.complete { font-weight: 700; color: #fff; background: #3f8f66; }
.trace-timeline { max-height: 580px; padding: 8px 10px 0; overflow: auto; }
.trace-event { padding: 10px 12px; background: #f8faf9; border: 1px solid #e3e9e5; border-radius: 7px; }
.trace-event header, .trace-event footer { display: flex; align-items: center; justify-content: space-between; }
.trace-event header span { display: flex; gap: 7px; align-items: center; color: #315943; }
.trace-event p { margin: 5px 0; font-size: 10px; color: #68766f; }
.trace-event footer { margin-top: 7px; font-size: 9px; color: #87938d; }
@media (max-width: 900px) {
  .history-summary { grid-template-columns: repeat(2, 1fr); }
  .history-filters { align-items: stretch; flex-direction: column; }
  .prefecture-filter { width: 100%; }
  .source-note { margin-left: 0; }
}
</style>
