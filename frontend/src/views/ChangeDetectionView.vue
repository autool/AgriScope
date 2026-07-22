<script setup lang="ts">
import {
  CloudOutlined,
  DiffOutlined,
  FileSearchOutlined,
  ImportOutlined,
  PlusOutlined,
  RadarChartOutlined,
  ReloadOutlined,
  WarningOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref, watch } from 'vue'

import ChangeCandidateImportModal from '@/components/changeDetection/ChangeCandidateImportModal.vue'
import ChangeCandidateDiscoveryModal from '@/components/changeDetection/ChangeCandidateDiscoveryModal.vue'
import ChangeCandidateMap from '@/components/changeDetection/ChangeCandidateMap.vue'
import ChangeCandidateReviewDrawer from '@/components/changeDetection/ChangeCandidateReviewDrawer.vue'
import ChangeImageryComparison from '@/components/changeDetection/ChangeImageryComparison.vue'
import ChangeRunCreateModal from '@/components/changeDetection/ChangeRunCreateModal.vue'
import { useChangeDetectionStore } from '@/store/changeDetectionStore'
import { useUserStore } from '@/store/userStore'
import type {
  ChangeCandidateImportPayload,
  ChangeCandidateDiscoveryPayload,
  ChangeCandidateReviewPayload,
  ChangeCandidateStatus,
  ChangeDetectionRun,
  ChangeRunCreatePayload,
} from '@/types/changeDetection'
import { CHANGE_CLASS_LABELS } from '@/types/changeDetection'

const changeStore = useChangeDetectionStore()
const userStore = useUserStore()
const {
  overviewRef,
  selectedRunCodeRef,
  selectedCandidateComputed,
  loadingRef,
  savingRef,
  comparisonRef,
  comparisonLoadingRef,
  comparisonErrorRef,
} = storeToRefs(changeStore)

const createModalOpenRef = ref<boolean>(false)
const importModalOpenRef = ref<boolean>(false)
const discoveryModalOpenRef = ref<boolean>(false)
const reviewDrawerOpenRef = ref<boolean>(false)
const statusFilterRef = ref<ChangeCandidateStatus | 'all'>('all')
const workspaceModeRef = ref<'comparison' | 'candidates'>('comparison')

const currentUserCodeComputed = computed<string | null>(() => (
  userStore.currentUserComputed?.user_code || null
))
const canRunComputed = computed<boolean>(() => (
  userStore.hasCapability('run_change_detection')
))
const canReviewComputed = computed<boolean>(() => (
  userStore.hasCapability('review_change_candidate')
))
const selectedRunComputed = computed<ChangeDetectionRun | null>(() => (
  changeStore.selectedRunComputed
))
const eligibleImageryComputed = computed(() => (
  overviewRef.value?.imagery.filter((asset) => asset.eligible) || []
))
const filteredCandidatesComputed = computed(() => {
  const candidates = selectedRunComputed.value?.candidates || []
  if (statusFilterRef.value === 'all') return candidates
  return candidates.filter((candidate) => candidate.status === statusFilterRef.value)
})

const statusLabel = (status: string): string => ({
  active: '待导入候选',
  reviewing: '判读中',
  completed: '已完成',
  cancelled: '已取消',
  pending: '待判读',
  confirmed: '已确认',
  excluded: '已排除',
}[status] || status)

const statusColor = (status: string): string => ({
  active: 'blue',
  reviewing: 'orange',
  completed: 'green',
  pending: 'orange',
  confirmed: 'green',
  excluded: 'default',
}[status] || 'default')

const createRun = async (payload: ChangeRunCreatePayload): Promise<void> => {
  try {
    await changeStore.createRun(payload)
    createModalOpenRef.value = false
    message.success('变化检测任务已创建，影像、规则和任务范围快照已固化')
  } catch {
    // 请求拦截器已显示安全错误。
  }
}

const importCandidates = async (
  payload: ChangeCandidateImportPayload,
): Promise<void> => {
  const run = selectedRunComputed.value
  if (!run) return
  try {
    const result = await changeStore.importCandidates(run.run_code, payload)
    importModalOpenRef.value = false
    message.success(`候选批次 ${result.batch_code} 已原子导入 ${result.imported_count} 个图斑`)
  } catch {
    // 请求拦截器已显示安全错误。
  }
}

const discoverCandidates = async (
  payload: ChangeCandidateDiscoveryPayload,
): Promise<void> => {
  const run = selectedRunComputed.value
  if (!run) return
  try {
    const result = await changeStore.discoverCandidates(run.run_code, payload)
    discoveryModalOpenRef.value = false
    workspaceModeRef.value = 'candidates'
    message.success(
      `自动发现 ${result.detected_count} 个连通域，入库 ${result.imported_count} 个未分类候选，过滤 ${result.filtered_below_area_count} 个小面积结果`,
    )
  } catch {
    // 请求拦截器已显示安全错误。
  }
}

const openCandidate = (candidateCode: string): void => {
  changeStore.selectCandidate(candidateCode)
  reviewDrawerOpenRef.value = true
}

const reviewCandidate = async (
  payload: ChangeCandidateReviewPayload,
): Promise<void> => {
  const run = selectedRunComputed.value
  const candidate = selectedCandidateComputed.value
  if (!run || !candidate) return
  try {
    await changeStore.reviewCandidate(
      run.run_code,
      candidate.candidate_code,
      payload,
    )
    message.success('判读结论已保存并追加不可变审计历史')
  } catch {
    // 请求拦截器已显示安全错误。
  }
}

onMounted(() => {
  void changeStore.load()
})

watch(selectedRunCodeRef, (runCode) => {
  if (runCode) void changeStore.loadComparison(runCode)
}, { immediate: true })
</script>

<template>
  <div class="change-view">
    <header class="page-heading">
      <span><DiffOutlined /><i><small>MULTI-TEMPORAL CHANGE</small><strong>多时相变化检测</strong><em>真实影像绑定、候选生产、六类判读与审计闭环</em></i></span>
      <div>
        <a-tag color="green">{{ eligibleImageryComputed.length }} 期可用影像</a-tag>
        <a-button :loading="loadingRef" @click="changeStore.load"><ReloadOutlined /> 刷新</a-button>
        <a-button
          type="primary"
          :disabled="!canRunComputed || eligibleImageryComputed.length < 2"
          @click="createModalOpenRef = true"
        >
          <PlusOutlined /> 新建检测任务
        </a-button>
      </div>
    </header>

    <a-spin :spinning="loadingRef">
      <template v-if="overviewRef">
        <a-alert
          v-for="blocker in overviewRef.blockers"
          :key="blocker"
          class="blocker-alert"
          type="warning"
          show-icon
          :message="blocker"
        />

        <section class="imagery-strip">
          <article
            v-for="asset in overviewRef.imagery"
            :key="asset.asset_code"
            :class="{ disabled: !asset.eligible }"
          >
            <CloudOutlined />
            <span>
              <strong>{{ asset.asset_name }}</strong>
              <small>{{ asset.asset_code }} · {{ asset.acquired_at.slice(0, 10) }}</small>
              <em>{{ asset.sensor_type }} · {{ asset.resolution_m ?? '--' }}m · {{ asset.crs || 'CRS 未知' }}</em>
            </span>
            <a-tooltip :title="asset.eligibility_reason || '实体、校验和与预处理状态均有效'">
              <a-tag :color="asset.eligible ? 'green' : 'default'">{{ asset.eligible ? '可用于检测' : '不可用' }}</a-tag>
            </a-tooltip>
          </article>
          <a-empty v-if="!overviewRef.imagery.length" description="尚未上传真实影像实体" />
        </section>

        <section class="workspace">
          <aside class="run-panel">
            <header><span><DiffOutlined /> 检测任务</span><strong>{{ overviewRef.runs.length }}</strong></header>
            <a-empty v-if="!overviewRef.runs.length" description="尚未创建变化检测任务" />
            <button
              v-for="run in overviewRef.runs"
              :key="run.run_code"
              type="button"
              :class="{ active: run.run_code === selectedRunCodeRef }"
              @click="changeStore.selectRun(run.run_code)"
            >
              <span><strong>{{ run.run_name }}</strong><small>{{ run.run_code }}</small></span>
              <a-tag :color="statusColor(run.status)">{{ statusLabel(run.status) }}</a-tag>
              <dl>
                <div><dt>候选</dt><dd>{{ run.candidate_count }}</dd></div>
                <div><dt>待判</dt><dd>{{ run.pending_count }}</dd></div>
                <div><dt>确认</dt><dd>{{ run.confirmed_count }}</dd></div>
              </dl>
            </button>
          </aside>

          <main v-if="selectedRunComputed" class="run-workspace">
            <section class="run-summary">
              <div class="temporal-pair">
                <article><small>BASELINE</small><strong>{{ selectedRunComputed.baseline_asset_code }}</strong></article>
                <DiffOutlined />
                <article><small>TARGET</small><strong>{{ selectedRunComputed.target_asset_code }}</strong></article>
              </div>
              <dl>
                <div><dt>规则版本</dt><dd>v{{ selectedRunComputed.rule_config_version }}</dd></div>
                <div><dt>任务图斑快照</dt><dd>{{ selectedRunComputed.task_plot_count.toLocaleString() }}</dd></div>
                <div><dt>配准偏差</dt><dd>{{ selectedRunComputed.alignment_offset_pixels }} px</dd></div>
                <div><dt>范围重叠</dt><dd>{{ (selectedRunComputed.alignment_overlap_ratio * 100).toFixed(1) }}%</dd></div>
              </dl>
              <div class="run-actions">
                <a-button
                  type="primary"
                  :disabled="!canRunComputed || selectedRunComputed.status !== 'active'"
                  @click="discoveryModalOpenRef = true"
                >
                  <RadarChartOutlined /> 自动发现候选
                </a-button>
                <a-button
                  :disabled="!canRunComputed || selectedRunComputed.status !== 'active'"
                  @click="importModalOpenRef = true"
                >
                  <ImportOutlined /> 导入外部 GeoJSON
                </a-button>
              </div>
            </section>

            <section class="analysis-area">
              <header class="workspace-switch">
                <a-radio-group v-model:value="workspaceModeRef" button-style="solid" size="small">
                  <a-radio-button value="comparison"><DiffOutlined /> 影像同步对比</a-radio-button>
                  <a-radio-button value="candidates"><FileSearchOutlined /> 候选专题与队列</a-radio-button>
                </a-radio-group>
                <span v-if="comparisonRef">公共网格 {{ comparisonRef.width }} × {{ comparisonRef.height }}</span>
              </header>

              <ChangeImageryComparison
                v-if="workspaceModeRef === 'comparison'"
                :metadata="comparisonRef"
                :loading="comparisonLoadingRef"
                :error="comparisonErrorRef"
                @retry="changeStore.loadComparison(selectedRunComputed.run_code)"
              />

              <section v-else class="map-queue">
                <div class="map-shell">
                  <ChangeCandidateMap
                    :feature-collection="selectedRunComputed.feature_collection"
                    :selected-candidate-code="selectedCandidateComputed?.candidate_code || ''"
                    @candidate-selected="openCandidate"
                  />
                  <div class="map-legend">
                    <strong>六类变化</strong>
                    <span v-for="(label, value) in CHANGE_CLASS_LABELS" :key="value">
                      <i :class="value" />{{ label }}
                    </span>
                  </div>
                  <div class="map-attribution">影像 © Esri, Maxar, Earthstar Geographics</div>
                </div>

                <aside class="candidate-queue">
                  <header>
                    <span><FileSearchOutlined /> 候选判读队列</span>
                    <a-select v-model:value="statusFilterRef" size="small">
                      <a-select-option value="all">全部</a-select-option>
                      <a-select-option value="pending">待判读</a-select-option>
                      <a-select-option value="confirmed">已确认</a-select-option>
                      <a-select-option value="excluded">已排除</a-select-option>
                    </a-select>
                  </header>
                  <a-empty v-if="!filteredCandidatesComputed.length" description="当前筛选没有候选" />
                  <button
                    v-for="candidate in filteredCandidatesComputed"
                    :key="candidate.candidate_code"
                    type="button"
                    :class="{ active: candidate.candidate_code === selectedCandidateComputed?.candidate_code }"
                    @click="openCandidate(candidate.candidate_code)"
                  >
                    <span>
                      <strong>{{ candidate.candidate_code }}</strong>
                      <small>{{ CHANGE_CLASS_LABELS[candidate.change_class] }}</small>
                    </span>
                    <a-tag :color="statusColor(candidate.status)">{{ statusLabel(candidate.status) }}</a-tag>
                    <dl>
                      <div><dt>面积</dt><dd>{{ candidate.area_ha.toFixed(4) }} ha</dd></div>
                      <div><dt>置信度</dt><dd>{{ (candidate.confidence * 100).toFixed(1) }}%</dd></div>
                    </dl>
                  </button>
                </aside>
              </section>
            </section>
          </main>

          <main v-else class="run-empty">
            <WarningOutlined />
            <strong>尚未建立检测任务</strong>
            <p>上传并完成两期真实影像预处理与双景自动配准后，创建任务以固化影像校验值、规则版本、任务图斑范围和实体配准成果。</p>
          </main>
        </section>
      </template>
    </a-spin>

    <ChangeRunCreateModal
      :open="createModalOpenRef"
      :imagery="overviewRef?.imagery || []"
      :registrations="overviewRef?.registrations || []"
      :operator-code="currentUserCodeComputed"
      :saving="savingRef"
      @close="createModalOpenRef = false"
      @create="createRun"
    />
    <ChangeCandidateImportModal
      :open="importModalOpenRef"
      :run-code="selectedRunComputed?.run_code || ''"
      :operator-code="currentUserCodeComputed"
      :saving="savingRef"
      @close="importModalOpenRef = false"
      @import="importCandidates"
    />
    <ChangeCandidateDiscoveryModal
      :open="discoveryModalOpenRef"
      :run-code="selectedRunComputed?.run_code || ''"
      :operator-code="currentUserCodeComputed"
      :saving="savingRef"
      @close="discoveryModalOpenRef = false"
      @discover="discoverCandidates"
    />
    <ChangeCandidateReviewDrawer
      :open="reviewDrawerOpenRef"
      :candidate="selectedCandidateComputed"
      :reviewer-code="currentUserCodeComputed"
      :saving="savingRef"
      :can-review="canReviewComputed"
      @close="reviewDrawerOpenRef = false"
      @review="reviewCandidate"
    />
  </div>
</template>

<style scoped>
.change-view { height: 100%; padding: 12px; overflow: auto; background: #eef2ef; }
.page-heading, .page-heading > span, .page-heading > div, .imagery-strip article, .run-panel header, .candidate-queue header, .run-summary, .temporal-pair { display: flex; align-items: center; }
.page-heading { justify-content: space-between; padding: 13px 15px; background: #fff; border: 1px solid #dce5df; border-radius: 8px; }
.page-heading > span { gap: 10px; color: #3d8661; }
.page-heading > span > :first-child { font-size: 25px; }
.page-heading i { display: flex; flex-direction: column; font-style: normal; }
.page-heading small { font-size: 8px; color: #87958e; }
.page-heading strong { font-size: 14px; color: #28372f; }
.page-heading em { font-size: 8px; font-style: normal; color: #68776f; }
.page-heading > div { gap: 7px; }
.blocker-alert { margin-top: 8px; }
.imagery-strip { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin: 8px 0; }
.imagery-strip article { gap: 9px; min-width: 0; padding: 10px 12px; background: #fff; border: 1px solid #dce5df; border-radius: 7px; }
.imagery-strip article.disabled { opacity: .65; }
.imagery-strip article > :first-child { flex: 0 0 auto; font-size: 20px; color: #40865f; }
.imagery-strip article span { display: flex; flex: 1; flex-direction: column; min-width: 0; }
.imagery-strip article strong, .imagery-strip article small, .imagery-strip article em { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.imagery-strip article strong { font-size: 11px; }
.imagery-strip article small, .imagery-strip article em { font-size: 8px; color: #7a8981; }
.imagery-strip article em { font-style: normal; }
.workspace { display: grid; grid-template-columns: 230px minmax(0, 1fr); min-height: 600px; background: #fff; border: 1px solid #dce5df; border-radius: 8px; overflow: hidden; }
.run-panel { padding: 10px; overflow: auto; background: #f8faf8; border-right: 1px solid #dce5df; }
.run-panel header, .candidate-queue header { justify-content: space-between; padding: 4px 3px 9px; font-size: 11px; }
.run-panel header span, .candidate-queue header span { display: flex; gap: 6px; align-items: center; font-weight: 700; }
.run-panel > button, .candidate-queue > button { width: 100%; padding: 9px; margin-bottom: 6px; text-align: left; background: #fff; border: 1px solid #dfe7e2; border-radius: 6px; cursor: pointer; }
.run-panel > button.active, .candidate-queue > button.active { border-color: #4f9b72; box-shadow: inset 3px 0 #4f9b72; }
.run-panel button > span, .candidate-queue button > span { display: inline-flex; flex-direction: column; max-width: 145px; vertical-align: middle; }
.run-panel button > .ant-tag, .candidate-queue button > .ant-tag { float: right; margin-right: 0; }
.run-panel button strong, .candidate-queue button strong { overflow: hidden; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.run-panel button small, .candidate-queue button small { font-size: 8px; color: #7d8a83; }
.run-panel dl, .candidate-queue dl, .run-summary dl { display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; margin: 8px 0 0; }
.run-panel dl div, .candidate-queue dl div, .run-summary dl div { padding: 4px; background: #f4f7f5; border-radius: 4px; }
.run-panel dt, .candidate-queue dt, .run-summary dt { font-size: 7px; color: #84918a; }
.run-panel dd, .candidate-queue dd, .run-summary dd { margin: 1px 0 0; font-size: 9px; font-weight: 700; }
.run-workspace { display: grid; grid-template-rows: auto minmax(0, 1fr); min-width: 0; }
.run-summary { gap: 14px; justify-content: space-between; padding: 10px 12px; border-bottom: 1px solid #dce5df; }
.temporal-pair { gap: 8px; }
.temporal-pair article { display: flex; flex-direction: column; min-width: 120px; padding: 7px; background: #f3f7f4; border-radius: 5px; }
.temporal-pair small { font-size: 7px; color: #84918a; }
.temporal-pair strong { font-size: 10px; }
.run-summary dl { flex: 1; grid-template-columns: repeat(4, minmax(80px, 1fr)); max-width: 520px; margin: 0; }
.run-actions { display: flex; gap: 6px; }
.analysis-area { display: grid; grid-template-rows: auto minmax(0, 1fr); min-height: 0; }
.workspace-switch { display: flex; align-items: center; justify-content: space-between; padding: 6px 9px; background: #f5f8f6; border-bottom: 1px solid #dce5df; }
.workspace-switch > span { font-size: 8px; color: #718077; }
.map-queue { display: grid; grid-template-columns: minmax(0, 1fr) 300px; min-height: 0; }
.map-shell { position: relative; min-height: 520px; overflow: hidden; }
.map-legend { position: absolute; top: 10px; left: 10px; display: grid; grid-template-columns: repeat(2, auto); gap: 4px 12px; padding: 9px; font-size: 8px; background: rgb(255 255 255 / 92%); border: 1px solid #d9e2dc; border-radius: 6px; }
.map-legend strong { grid-column: 1 / -1; }
.map-legend span { display: flex; gap: 5px; align-items: center; }
.map-legend i { width: 12px; height: 3px; background: #d87b38; }
.map-legend i.unclassified { background: #d4a13d; }
.map-legend i.suspected_construction { background: #e0573e; }
.map-legend i.farmland_outflow { background: #cf7a2a; }
.map-legend i.construction_facility_change { background: #9d5b43; }
.map-legend i.non_farmland_agricultural_change { background: #7864b7; }
.map-legend i.unused_land_change { background: #71828c; }
.map-legend i.farmland_attribute_change { background: #2f8c63; }
.map-attribution { position: absolute; right: 7px; bottom: 7px; padding: 3px 6px; font-size: 8px; color: #526159; background: rgb(255 255 255 / 82%); border-radius: 3px; }
.candidate-queue { padding: 9px; overflow: auto; background: #fbfcfb; border-left: 1px solid #dce5df; }
.candidate-queue dl { grid-template-columns: 1fr 1fr; clear: both; }
.run-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; color: #6f7d76; }
.run-empty > :first-child { margin-bottom: 12px; font-size: 38px; color: #d49a45; }
.run-empty p { max-width: 520px; font-size: 11px; text-align: center; }
@media (max-width: 1180px) {
  .imagery-strip { grid-template-columns: 1fr 1fr; }
  .workspace { grid-template-columns: 190px minmax(0, 1fr); }
  .map-queue { grid-template-columns: minmax(0, 1fr) 260px; }
  .run-summary dl { display: none; }
}
</style>
