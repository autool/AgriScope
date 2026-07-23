<script setup lang="ts">
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, ref } from 'vue'

import { useReviewStore } from '@/store/reviewStore'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'

const workbenchStore = useWorkbenchStore()
const reviewStore = useReviewStore()
const userStore = useUserStore()
const { overviewRef, plotVersionsRef } = storeToRefs(workbenchStore)
const { loadingRef } = storeToRefs(reviewStore)
const { currentUserComputed } = storeToRefs(userStore)
const commentRef = ref<string>('')
const issueTypeRef = ref<string>('boundary_offset')
const reviewNodeComputed = computed<{
  capability: string
  roleName: string
} | null>(() => ({
  self_check: { capability: 'review_self_check', roleName: '内业解译员' },
  quality_review: { capability: 'review_quality', roleName: '质检员' },
  client_review: { capability: 'review_client', roleName: '甲方（监管方）' },
})[overviewRef.value?.task.status || ''] || null)
const canReviewComputed = computed<boolean>(() => (
  Boolean(reviewNodeComputed.value)
  && userStore.hasCapability(reviewNodeComputed.value?.capability || '')
))
const reviewStepComputed = computed<number>(() => ({
  self_check: 0,
  quality_review: 1,
  client_review: 2,
  completed: 3,
})[overviewRef.value?.task.status || ''] ?? -1)
const reviewReadinessComputed = computed<{
  type: 'success' | 'info' | 'warning' | 'error'
  title: string
  description: string
  passBlocked: boolean
}>(() => {
  const overview = overviewRef.value
  const status = overview?.task.status
  const openIssues = overview?.statistics.open_issue_count || 0
  const pendingField = overview?.statistics.pending_field_verification_count || 0
  if (status === 'interpreting') {
    return {
      type: 'info',
      title: '任务尚未进入三级审核',
      description: '需先完成全量质量检查并由内业解译员提交内业自检。',
      passBlocked: true,
    }
  }
  if (status === 'rejected') {
    return {
      type: 'error',
      title: '任务已被驳回',
      description: '请根据最近审核意见重新组织整改，当前不能继续执行通过操作。',
      passBlocked: true,
    }
  }
  if (status === 'completed') {
    return {
      type: 'success',
      title: '三级审核已经完成',
      description: '可由项目负责人进入成果交付页面生成当前任务成果包。',
      passBlocked: true,
    }
  }
  const blockers: string[] = []
  if (status === 'quality_review' && openIssues > 0) {
    blockers.push(`${openIssues} 条质量问题未关闭`)
  }
  if (status === 'client_review') {
    if (openIssues > 0) blockers.push(`${openIssues} 条质量问题未关闭`)
    if (pendingField > 0) blockers.push(`${pendingField} 条外业疑点未处置`)
  }
  if (blockers.length > 0) {
    return {
      type: 'warning',
      title: '当前节点尚不具备通过条件',
      description: blockers.join('；'),
      passBlocked: true,
    }
  }
  return {
    type: 'success',
    title: '当前节点业务门禁已满足',
    description: reviewNodeComputed.value
      ? `具备 ${reviewNodeComputed.value.roleName} 职责的项目用户可以执行审核。`
      : '等待任务进入审核节点。',
    passBlocked: !reviewNodeComputed.value,
  }
})
const canPassComputed = computed<boolean>(() => (
  canReviewComputed.value && !reviewReadinessComputed.value.passBlocked
))
const canRollbackComputed = computed<boolean>(() => (
  userStore.hasCapability('rollback_plot')
))
const recentReviewsComputed = computed(() => overviewRef.value?.reviews || [])
const qualityScoreComputed = computed<number | null>(() => (
  overviewRef.value?.task.quality_score ?? null
))

const taskStatusLabel = (status: string): string => ({
  interpreting: '解译整改中',
  self_check: '内业自检',
  quality_review: '质检审核',
  client_review: '甲方复核',
  completed: '审核完成',
  rejected: '审核驳回',
})[status] || status

const reviewLevelLabel = (level: string): string => ({
  interpretation: '地块解译',
  quality: '质量检查',
  self_check: '内业自检',
  quality_review: '质检审核',
  client_review: '甲方复核',
  quality_issue: '问题整改',
  field_verification: '外业核查',
  delivery: '成果交付',
  disaster: '灾害监测',
  disaster_monitoring: '灾害监测',
  statistics: '面积统计',
  imagery: '影像处理',
  imagery_processing: '影像处理',
  version_management: '版本管理',
})[level] || level

const reviewActionLabel = (action: string): string => ({
  pass: '通过',
  return: '退回',
  reject: '驳回',
  submitted: '提交',
  issue_resolved: '问题关闭',
  plot_source_imported: '数据导入',
  quality_checked: '质量检查',
  task_quality_checked: '全量质检',
  quality_batch_run: '全量质检',
  quality_evidence_invalidated: '旧质检证据失效',
  processing_step_executed: '处理执行',
  processing_step_completed: '产物登记',
  imagery_asset_imported: '影像导入',
  delivery_package_generated: '成果包生成',
  rollback: '版本回退',
})[action] || action

const formatReviewTime = (value: string): string => new Date(value).toLocaleString(
  'zh-CN',
  { hour12: false },
)

/**
 * 执行审核动作。
 * Args:
 *   action: 通过、退回或驳回。
 * Returns:
 *   Promise<void>: 审核状态更新完成后结束。
 */
const handleAction = async (
  action: 'pass' | 'return' | 'reject',
): Promise<void> => {
  if (action === 'pass' && !canPassComputed.value) {
    message.warning(reviewReadinessComputed.value.description)
    return
  }
  if (action !== 'pass' && !commentRef.value.trim()) {
    message.warning('退回或驳回必须填写审核意见')
    return
  }
  try {
    await reviewStore.executeAction(
      action,
      commentRef.value || '审核通过',
      issueTypeRef.value,
    )
    commentRef.value = ''
    message.success('审核操作已记录')
  } catch {
    // 由请求拦截器展示服务端权限或状态提示。
  }
}

const handleRollback = async (targetVersion: number): Promise<void> => {
  try {
    await reviewStore.rollback(targetVersion)
    message.success(`已恢复历史版本 v${targetVersion}，任务重新进入整改`)
  } catch {
    // 由请求拦截器展示服务端权限或版本校验提示。
  }
}
</script>

<template>
  <section class="panel">
    <header>
      <span><small>三级成果审核</small><strong>{{ taskStatusLabel(overviewRef?.task.status || '') }}</strong></span>
      <a-tag :color="qualityScoreComputed !== null ? 'blue' : 'default'">
        {{ qualityScoreComputed !== null ? `${qualityScoreComputed} 分` : '暂无任务得分' }}
      </a-tag>
    </header>
    <a-steps
      direction="vertical"
      size="small"
      :current="reviewStepComputed"
      :status="overviewRef?.task.status === 'rejected' ? 'error' : 'process'"
    >
      <a-step title="内业自检" />
      <a-step title="质检审核" />
      <a-step title="甲方复核" />
    </a-steps>
    <a-alert
      class="readiness-alert"
      show-icon
      :type="reviewReadinessComputed.type"
      :message="reviewReadinessComputed.title"
      :description="reviewReadinessComputed.description"
    />
    <div class="identity-card" :class="{ denied: reviewNodeComputed && !canReviewComputed }">
      <span>
        <small>当前项目身份</small>
        <strong>{{ currentUserComputed?.display_name || '未加载' }} · {{ currentUserComputed?.role_name || '--' }}</strong>
      </span>
      <a-tag :color="canReviewComputed ? 'green' : 'default'">
        {{ reviewNodeComputed ? `本节点需 ${reviewNodeComputed.roleName}` : '当前无待审节点' }}
      </a-tag>
    </div>
    <a-alert
      v-if="reviewNodeComputed && !canReviewComputed"
      type="warning"
      show-icon
      :message="`当前角色不能处理${reviewNodeComputed.roleName}节点`"
      description="可从顶部身份菜单切换到项目内具备该职责的用户；后端仍会再次校验角色。"
    />
    <div v-if="reviewNodeComputed" class="form">
      <label>问题类型</label>
      <a-select
        v-model:value="issueTypeRef"
        style="width: 100%"
        :disabled="!canReviewComputed"
        :options="[
          { value: 'boundary_offset', label: '边界偏差' },
          { value: 'attribute_error', label: '属性错误' },
        ]"
      />
      <label>审核意见</label>
      <a-textarea
        v-model:value="commentRef"
        :rows="3"
        :disabled="!canReviewComputed"
      />
      <div class="actions">
        <a-button
          type="primary"
          :disabled="!canPassComputed"
          :loading="loadingRef"
          @click="handleAction('pass')"
        >
          通过
        </a-button>
        <a-button :disabled="!canReviewComputed" @click="handleAction('return')">
          退回
        </a-button>
        <a-button danger :disabled="!canReviewComputed" @click="handleAction('reject')">
          驳回
        </a-button>
      </div>
    </div>
    <div class="audit-history">
      <h3>
        <span>当前整改周期记录</span>
        <small>
          显示 {{ recentReviewsComputed.length }} /
          {{ overviewRef?.statistics.current_cycle_review_count || 0 }} 条 ·
          全历史 {{ overviewRef?.statistics.review_record_count || 0 }} 条
        </small>
      </h3>
      <a-empty v-if="recentReviewsComputed.length === 0" description="暂无审核审计记录" />
      <article v-for="record in recentReviewsComputed" :key="`${record.created_at}-${record.action}`">
        <i />
        <span>
          <strong>{{ reviewLevelLabel(record.review_level) }} · {{ reviewActionLabel(record.action) }}</strong>
          <small>{{ record.reviewer }} · {{ record.reviewer_code || '历史记录无稳定编码' }} · {{ formatReviewTime(record.created_at) }}</small>
          <small v-if="record.quality_run_code">绑定质检批次 {{ record.quality_run_code }}</small>
          <em>{{ record.comment || '未填写说明' }}</em>
        </span>
        <a-tag>{{ record.reviewer_role || '历史角色' }}</a-tag>
      </article>
    </div>
    <div class="versions">
      <h3>当前图斑版本</h3><div v-for="version in plotVersionsRef?.versions || []" :key="version.version">
        <span><strong>v{{ version.version }}</strong><small>{{ version.change_summary }}</small></span><a-button
          v-if="version.version !== plotVersionsRef?.current_version"
          type="link"
          size="small"
          :disabled="!canRollbackComputed"
          :title="canRollbackComputed ? '恢复该历史版本' : '仅质检员或项目负责人可回退版本'"
          @click="handleRollback(version.version)"
        >
          恢复
        </a-button><a-tag v-else color="green">当前</a-tag>
      </div>
    </div>
  </section>
</template>

<style scoped>
.panel { height: 100%; padding: 13px; overflow: auto; }
header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
header > span { display: flex; flex-direction: column; }
small { font-size: 7px; color: #8b9690; }
header strong { font-size: 12px; }
.form { padding-top: 12px; margin-top: 8px; border-top: 1px solid #e6eae8; }
.readiness-alert { margin: 9px 0; }
.identity-card { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 9px; margin: 10px 0 8px; background: #f3f8f5; border: 1px solid #dbe8e0; border-radius: 6px; }
.identity-card.denied { background: #fff9ef; border-color: #eee0bd; }
.identity-card > span { display: flex; flex-direction: column; }
.identity-card strong { font-size: 9px; }
.form label { display: block; margin: 8px 0 4px; font-size: 8px; color: #68766f; }
.actions { display: grid; grid-template-columns: 1fr 1fr 0.8fr; gap: 5px; margin-top: 9px; }
.audit-history { padding-top: 12px; margin-top: 12px; border-top: 1px solid #e6eae8; }
.audit-history h3 { display: flex; align-items: center; justify-content: space-between; margin: 0 0 7px; font-size: 10px; }
.audit-history h3 small { font-weight: 400; }
.audit-history article { display: grid; grid-template-columns: 7px minmax(0, 1fr) auto; gap: 7px; align-items: start; padding: 8px 0; border-bottom: 1px solid #edf0ee; }
.audit-history article > i { width: 7px; height: 7px; margin-top: 4px; background: #4b946c; border-radius: 50%; }
.audit-history article > span { display: flex; min-width: 0; flex-direction: column; }
.audit-history article strong { font-size: 8px; }
.audit-history article small, .audit-history article em { overflow: hidden; font-size: 7px; color: #8b9690; text-overflow: ellipsis; white-space: nowrap; }
.audit-history article em { margin-top: 2px; font-style: normal; color: #5e6e66; }
.versions { padding-top: 12px; margin-top: 12px; border-top: 1px solid #e6eae8; }
.versions h3 { font-size: 10px; }
.versions > div { display: flex; align-items: center; justify-content: space-between; min-height: 43px; border-bottom: 1px solid #edf0ee; }
.versions > div > span { display: flex; flex-direction: column; }
.versions strong { font-size: 9px; }
</style>
