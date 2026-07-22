<script setup lang="ts">
import {
  AimOutlined,
  CheckOutlined,
  EditOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref, watch } from 'vue'

import BatchAttributeModal from '@/components/editing/BatchAttributeModal.vue'
import { useQualityIssueStore } from '@/store/qualityIssueStore'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type { QualityIssueItem, QualityIssueQuery } from '@/types/workbench'
import { formatArea } from '@/utils/area'

const qualityIssueStore = useQualityIssueStore()
const workbenchStore = useWorkbenchStore()
const userStore = useUserStore()
const {
  queryRef,
  resultRef,
  loadingRef,
  errorRef,
  resolvingIssueIdRef,
  itemsComputed,
  ruleOptionsComputed,
} = storeToRefs(qualityIssueStore)
const keywordRef = ref<string>('')
const locatingPlotCodeRef = ref<string | null>(null)
const selectedPlotCodesRef = ref<string[]>([])
const batchModalOpenRef = ref<boolean>(false)
const resolveModalOpenRef = ref<boolean>(false)
const resolvingIssueRef = ref<QualityIssueItem | null>(null)
const resolutionCommentRef = ref<string>('')
const canResolveReviewIssuesComputed = computed<boolean>(() => (
  userStore.hasCapability('resolve_review_issue')
))
const canEditPlotsComputed = computed<boolean>(() => (
  userStore.hasCapability('edit_plots')
))

const severityColor = (severity: QualityIssueItem['severity']): string => ({
  high: 'error',
  medium: 'warning',
  low: 'default',
})[severity]

const severityLabel = (severity: QualityIssueItem['severity']): string => ({
  high: '高',
  medium: '中',
  low: '低',
})[severity]

const updateFilter = async <TKey extends keyof QualityIssueQuery>(
  key: TKey,
  value: QualityIssueQuery[TKey],
): Promise<void> => {
  await qualityIssueStore.updateFilters({ [key]: value })
}

const applyKeyword = async (): Promise<void> => {
  await qualityIssueStore.updateFilters({
    keyword: keywordRef.value.trim() || undefined,
  })
}

const focusIssue = async (issue: QualityIssueItem): Promise<void> => {
  if (!issue.plot_code) {
    message.warning('该问题没有关联图斑，无法在地图定位')
    return
  }
  locatingPlotCodeRef.value = issue.plot_code
  try {
    await workbenchStore.focusByCode(issue.plot_code)
    message.success(`已定位问题图斑 ${issue.plot_code}`)
  } catch {
    // 请求拦截器已显示安全错误，保留当前问题列表。
  } finally {
    locatingPlotCodeRef.value = null
  }
}

const togglePlotSelection = (plotCode: string | null): void => {
  if (!plotCode) return
  selectedPlotCodesRef.value = selectedPlotCodesRef.value.includes(plotCode)
    ? selectedPlotCodesRef.value.filter((item) => item !== plotCode)
    : [...selectedPlotCodesRef.value, plotCode]
}

const selectCurrentPage = (): void => {
  const pageCodes = itemsComputed.value
    .map((item) => item.plot_code)
    .filter((value): value is string => Boolean(value))
  selectedPlotCodesRef.value = [...new Set([
    ...selectedPlotCodesRef.value,
    ...pageCodes,
  ])]
}

const submitBatchAttributes = async (
  payload: Parameters<typeof workbenchStore.batchUpdatePlotAttributes>[0],
): Promise<void> => {
  try {
    const result = await workbenchStore.batchUpdatePlotAttributes(payload)
    batchModalOpenRef.value = false
    selectedPlotCodesRef.value = []
    await qualityIssueStore.load()
    message.success(
      `已更新 ${result.updated_count} 个图斑并生成新版本，请重新运行全量质检`,
    )
  } catch {
    // 后端返回任务作用域或属性逻辑错误时保留选择和表单。
  }
}

const openResolveModal = (issue: QualityIssueItem): void => {
  resolvingIssueRef.value = issue
  resolutionCommentRef.value = ''
  resolveModalOpenRef.value = true
}

const closeResolveModal = (): void => {
  resolveModalOpenRef.value = false
  resolvingIssueRef.value = null
  resolutionCommentRef.value = ''
}

const submitIssueResolution = async (): Promise<void> => {
  const issue = resolvingIssueRef.value
  const currentUser = userStore.currentUserComputed
  if (!issue || !currentUser) {
    message.warning('当前项目用户或问题信息尚未加载')
    return
  }
  if (!resolutionCommentRef.value.trim()) {
    message.warning('请填写整改复核和关闭依据')
    return
  }
  try {
    await qualityIssueStore.resolveReviewIssue(
      issue.id,
      currentUser.user_code,
      resolutionCommentRef.value.trim(),
    )
    closeResolveModal()
    message.success(`问题 ${issue.id} 已确认关闭并写入审核审计`)
  } catch {
    // 请求拦截器会显示角色、来源或状态校验结果。
  }
}

onMounted(() => {
  void qualityIssueStore.load(workbenchStore.taskCodeComputed)
})

watch(
  () => workbenchStore.taskQualityResultRef?.executed_at,
  (executedAt) => {
    if (executedAt) void qualityIssueStore.load(workbenchStore.taskCodeComputed)
  },
)
</script>

<template>
  <section class="issue-queue">
    <div class="summary-row">
      <span><small>未关闭</small><strong>{{ resultRef?.open_count || 0 }}</strong></span>
      <span class="high"><small>高风险</small><strong>{{ resultRef?.high_count || 0 }}</strong></span>
      <span class="medium"><small>中风险</small><strong>{{ resultRef?.medium_count || 0 }}</strong></span>
      <span><small>低风险</small><strong>{{ resultRef?.low_count || 0 }}</strong></span>
    </div>

    <div class="filters">
      <a-select
        size="small"
        :value="queryRef.status"
        :options="[
          { value: 'open', label: '未关闭' },
          { value: 'resolved', label: '已解决' },
          { value: 'all', label: '全部历史' },
        ]"
        @change="(value: QualityIssueQuery['status']) => updateFilter('status', value)"
      />
      <a-select
        allow-clear
        size="small"
        placeholder="全部规则"
        :value="queryRef.rule_code"
        :options="ruleOptionsComputed"
        @change="(value: string | undefined) => updateFilter('rule_code', value)"
      />
      <a-select
        allow-clear
        size="small"
        placeholder="全部风险"
        :value="queryRef.severity"
        :options="[
          { value: 'high', label: '高风险' },
          { value: 'medium', label: '中风险' },
          { value: 'low', label: '低风险' },
        ]"
        @change="(value: QualityIssueQuery['severity']) => updateFilter('severity', value)"
      />
      <a-select
        allow-clear
        size="small"
        placeholder="全部问题类型"
        :value="queryRef.issue_type"
        :options="[
          { value: 'quality_rule', label: '自动质检问题' },
          { value: 'field_verification', label: '外业核查问题' },
          { value: 'boundary_offset', label: '审核 · 边界偏差' },
          { value: 'attribute_error', label: '审核 · 属性错误' },
          { value: 'review_comment', label: '其他审核意见' },
        ]"
        @change="(value: string | undefined) => updateFilter('issue_type', value)"
      />
    </div>

    <div class="search-row">
      <a-input
        v-model:value="keywordRef"
        allow-clear
        size="small"
        placeholder="图斑、市、县区或权属村"
        @press-enter="applyKeyword"
      >
        <template #prefix><SearchOutlined /></template>
      </a-input>
      <a-button size="small" @click="applyKeyword">查询</a-button>
      <a-button size="small" aria-label="刷新问题列表" @click="qualityIssueStore.load()">
        <ReloadOutlined />
      </a-button>
    </div>

    <div class="selection-toolbar">
      <span>已选 {{ selectedPlotCodesRef.length }} 个图斑</span>
      <div>
        <button @click="selectCurrentPage">选择本页</button>
        <button :disabled="!selectedPlotCodesRef.length" @click="selectedPlotCodesRef = []">清空</button>
        <a-button
          size="small"
          type="primary"
          :disabled="!selectedPlotCodesRef.length || workbenchStore.overviewRef?.task.status !== 'interpreting' || !canEditPlotsComputed"
          @click="batchModalOpenRef = true"
        >
          <EditOutlined />批量赋值
        </a-button>
      </div>
    </div>

    <a-alert
      v-if="errorRef"
      type="error"
      show-icon
      :message="errorRef"
      class="queue-alert"
    />

    <a-spin :spinning="loadingRef">
      <div v-if="itemsComputed.length" class="issue-list">
        <article
          v-for="issue in itemsComputed"
          :key="issue.id"
          :class="{ selected: Boolean(issue.plot_code && selectedPlotCodesRef.includes(issue.plot_code)) }"
        >
          <header>
            <span>
              <a-checkbox
                :disabled="!issue.plot_code"
                :checked="Boolean(issue.plot_code && selectedPlotCodesRef.includes(issue.plot_code))"
                @click.stop
                @change="togglePlotSelection(issue.plot_code)"
              />
              <a-tag :color="severityColor(issue.severity)">
                {{ severityLabel(issue.severity) }}风险
              </a-tag>
              <strong>{{ issue.rule_label }}</strong>
            </span>
            <a-tag :color="issue.status === 'open' ? 'processing' : 'success'">
              {{ issue.status === 'open' ? '未关闭' : '已解决' }}
            </a-tag>
          </header>
          <button
            class="plot-link"
            :disabled="!issue.plot_code || locatingPlotCodeRef === issue.plot_code"
            @click="focusIssue(issue)"
          >
            <AimOutlined />
            {{ issue.plot_code || '任务级问题' }}
          </button>
          <p>{{ issue.description }}</p>
          <footer>
            <span>{{ [issue.city_name, issue.district_name].filter(Boolean).join(' / ') || '无行政区信息' }}</span>
            <span>{{ formatArea(issue.area_ha) }} 公顷 · v{{ issue.plot_version || '--' }}</span>
          </footer>
          <div v-if="issue.status === 'resolved' && issue.resolution_comment" class="resolution-note">
            {{ issue.resolved_by || '审核人员' }}：{{ issue.resolution_comment }}
          </div>
          <div
            v-if="issue.status === 'open' && issue.source === 'manual' && issue.rule_code.startsWith('REVIEW_')"
            class="issue-actions"
          >
            <span>人工审核问题需复核后关闭</span>
            <a-button
              size="small"
              :disabled="!canResolveReviewIssuesComputed"
              :loading="resolvingIssueIdRef === issue.id"
              @click="openResolveModal(issue)"
            >
              <CheckOutlined />确认关闭
            </a-button>
          </div>
        </article>
      </div>
      <a-empty v-else description="当前筛选条件下没有质量问题" />
    </a-spin>

    <a-pagination
      v-if="resultRef && resultRef.total_count > queryRef.page_size"
      size="small"
      show-less-items
      :current="queryRef.page"
      :page-size="queryRef.page_size"
      :total="resultRef.total_count"
      @change="qualityIssueStore.setPage"
    />

    <BatchAttributeModal
      :open="batchModalOpenRef"
      :plot-codes="selectedPlotCodesRef"
      :loading="workbenchStore.batchUpdatingPlotsRef"
      @cancel="batchModalOpenRef = false"
      @submit="submitBatchAttributes"
    />
    <a-modal
      :open="resolveModalOpenRef"
      title="确认关闭人工审核问题"
      ok-text="确认关闭"
      cancel-text="取消"
      :confirm-loading="resolvingIssueIdRef === resolvingIssueRef?.id"
      @ok="submitIssueResolution"
      @cancel="closeResolveModal"
    >
      <a-alert
        type="info"
        show-icon
        :message="resolvingIssueRef?.description || '请复核整改证据'"
      />
      <label class="resolution-field">
        <span>整改复核与关闭依据</span>
        <a-textarea
          v-model:value="resolutionCommentRef"
          :rows="4"
          placeholder="说明已核验的影像、边界、属性或外业证据"
        />
      </label>
    </a-modal>
  </section>
</template>

<style scoped lang="less">
.issue-queue {
  padding-top: 6px;
}

.summary-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  overflow: hidden;
  background: #fff;
  border: 1px solid #e1e8e4;
  border-radius: 5px;
}

.summary-row > span {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 6px 2px;
  border-right: 1px solid #e6ebe8;
}

.summary-row > span:last-child { border-right: 0; }
.summary-row small { font-size: 7px; color: #86928b; }
.summary-row strong { font-size: 12px; color: #46544d; }
.summary-row .high strong { color: #bd4337; }
.summary-row .medium strong { color: #a36f14; }

.filters {
  display: grid;
  grid-template-columns: 0.8fr 1.25fr 0.85fr 1fr;
  gap: 5px;
  margin-top: 7px;
}

.search-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 5px;
  margin-top: 6px;
}

.selection-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 33px;
  margin-top: 5px;
  font-size: 8px;
  color: #66746c;
  border-top: 1px dashed #dfe6e2;
  border-bottom: 1px dashed #dfe6e2;
}

.selection-toolbar > div {
  display: flex;
  gap: 6px;
  align-items: center;
}

.selection-toolbar button:not(.ant-btn) {
  padding: 0;
  font-size: 8px;
  color: #2d694c;
  cursor: pointer;
  background: transparent;
  border: 0;
}

.selection-toolbar button:disabled {
  color: #a4ada8;
  cursor: default;
}

.queue-alert { margin-top: 7px; }

.issue-list {
  margin-top: 7px;
  border-top: 1px solid #e1e7e4;
}

.issue-list article {
  padding: 8px 2px;
  border-bottom: 1px solid #e7ebe9;
}

.issue-list article.selected {
  margin: 0 -4px;
  padding-right: 6px;
  padding-left: 6px;
  background: #f0f8f3;
}

.issue-list header,
.issue-list header > span,
.issue-list footer,
.plot-link {
  display: flex;
  align-items: center;
}

.issue-list header {
  justify-content: space-between;
}

.issue-list header > span { gap: 4px; min-width: 0; }
.issue-list header strong { overflow: hidden; font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }

.plot-link {
  gap: 5px;
  padding: 5px 0 2px;
  font-family: ui-monospace, monospace;
  font-size: 8px;
  color: #286448;
  cursor: pointer;
  background: transparent;
  border: 0;
}

.plot-link:disabled { color: #9da7a2; cursor: default; }

.issue-list p {
  margin: 4px 0;
  font-size: 8px;
  line-height: 14px;
  color: #647169;
}

.issue-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 6px;
  margin-top: 5px;
  font-size: 8px;
  color: #7b6a3a;
  border-top: 1px dashed #e5dcc5;
}

.resolution-note {
  padding: 5px 6px;
  margin-top: 5px;
  font-size: 8px;
  color: #3d6c52;
  background: #edf7f0;
  border-radius: 4px;
}

.resolution-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 12px;
  font-size: 12px;
  color: #4e5d55;
}

.issue-list footer {
  justify-content: space-between;
  font-size: 7px;
  color: #8a958f;
}

:deep(.ant-pagination) {
  margin-top: 8px;
  text-align: right;
}
</style>
