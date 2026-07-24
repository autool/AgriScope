<script setup lang="ts">
import {
  CheckCircleOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, ref } from 'vue'

import QualityIssueQueue from '@/components/quality/QualityIssueQueue.vue'
import TaskQualityRunHistory from '@/components/quality/TaskQualityRunHistory.vue'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'

const workbenchStore = useWorkbenchStore()
const userStore = useUserStore()
const {
  overviewRef,
  canRunTaskQualityComputed,
  taskQualityCheckingRef,
  taskQualityResultRef,
} = storeToRefs(workbenchStore)

const commentRef = ref<string>('')

const taskStatusComputed = computed<string>(
  () => overviewRef.value?.task.status || 'interpreting',
)
const canRunComputed = computed<boolean>(() => (
  taskStatusComputed.value === 'interpreting'
  && canRunTaskQualityComputed.value
))
const canSubmitIdentityComputed = computed<boolean>(() => (
  userStore.hasCapability('submit_self_check')
))
// Pinia Store 在开发期新增字段时，旧 HMR 实例可能短暂缺少该字段。
// 通过 Store 直接读取并提供安全默认值，避免组件热替换阶段中断整页渲染。
const taskQualityRunsComputed = computed(() => (
  workbenchStore.taskQualityRunsRef ?? null
))
const taskQualityRunsErrorComputed = computed<string | null>(() => (
  workbenchStore.taskQualityRunsErrorRef ?? null
))
const taskQualityRunsLoadingComputed = computed<boolean>(() => (
  workbenchStore.taskQualityRunsLoadingRef ?? false
))
const taskSubmittingComputed = computed<boolean>(() => (
  workbenchStore.taskSubmittingRef ?? false
))
const canSubmitQualityRunComputed = computed<boolean>(() => (
  !taskQualityRunsErrorComputed.value
  && !taskQualityRunsLoadingComputed.value
  && taskQualityRunsComputed.value?.submission_eligible === true
))
const submissionBlockerComputed = computed<string>(() => (
  taskQualityRunsErrorComputed.value
  || taskQualityRunsComputed.value?.submission_blockers[0]
  || '正在核验最近全量质检批次与当前任务数据'
))
const coveragePercentComputed = computed<number>(() => {
  const result = taskQualityResultRef.value
  if (!result?.total_plot_count) return 0
  return Math.round(result.checked_plot_count / result.total_plot_count * 100)
})

const runFullQualityCheck = async (): Promise<void> => {
  if (!canRunTaskQualityComputed.value) {
    message.warning('当前项目身份无权执行全量质检')
    return
  }
  try {
    const result = await workbenchStore.runTaskQualityChecks(
      commentRef.value.trim(),
    )
    if (result.can_submit) {
      message.success(`全量质检完成，${result.passing_plot_count} 个图斑全部通过`)
    } else {
      message.warning(
        `全量质检完成，仍有 ${result.failed_plot_count} 个图斑需要整改`,
      )
    }
  } catch {
    // 请求拦截器已展示安全错误信息，保留填写内容便于重试。
  }
}

const submitForSelfCheck = async (): Promise<void> => {
  const currentUser = userStore.currentUserComputed
  if (!currentUser) {
    message.warning('当前项目用户尚未加载')
    return
  }
  if (!canSubmitIdentityComputed.value) {
    message.warning('只有内业解译员可以提交内业自检')
    return
  }
  if (!canSubmitQualityRunComputed.value) {
    message.warning(submissionBlockerComputed.value)
    return
  }
  try {
    await workbenchStore.submitTaskForSelfCheck(
      currentUser.user_code,
      commentRef.value.trim() || '全量质量检查完成，提交内业自检',
    )
    message.success('任务已提交至内业自检节点')
  } catch {
    // 后端会返回未覆盖或未通过的具体门禁原因。
  }
}
</script>

<template>
  <section class="task-quality-panel">
    <header>
      <span class="title-icon"><SafetyCertificateOutlined /></span>
      <span>
        <small>任务级质量门禁</small>
        <strong>全量图斑质量检查</strong>
      </span>
      <a-tag :color="taskStatusComputed === 'interpreting' ? 'processing' : 'blue'">
        {{ taskStatusComputed }}
      </a-tag>
    </header>

    <p class="description">
      按任务作用域一次检查 {{ overviewRef?.task.total_plots || 0 }} 个图斑；提交必须绑定最近一次仍与当前任务数据一致的全量质检批次。
    </p>

    <a-alert
      v-if="taskStatusComputed === 'interpreting' && !canSubmitQualityRunComputed"
      :message="submissionBlockerComputed"
      :type="taskQualityRunsErrorComputed ? 'error' : taskQualityRunsLoadingComputed ? 'info' : 'warning'"
      show-icon
      class="submission-alert"
    />

    <div class="operator-row">
      <span class="operator-identity">
        {{ userStore.currentUserComputed?.display_name || '--' }} ·
        {{ userStore.currentUserComputed?.role_name || '--' }}
      </span>
      <a-input v-model:value="commentRef" size="small" placeholder="执行说明（可选）" />
    </div>

    <div class="task-actions">
      <a-button
        type="primary"
        :loading="taskQualityCheckingRef"
        :disabled="!canRunComputed || taskSubmittingComputed"
        @click="runFullQualityCheck"
      >
        运行全量质检
      </a-button>
      <a-button
        :loading="taskSubmittingComputed"
        :disabled="taskStatusComputed !== 'interpreting' || taskQualityCheckingRef || taskQualityRunsLoadingComputed || !canSubmitIdentityComputed || !canSubmitQualityRunComputed"
        @click="submitForSelfCheck"
      >
        提交内业自检
      </a-button>
    </div>
    <small v-if="!canSubmitIdentityComputed" class="permission-hint">
      当前身份无提交权限，请切换为项目内业解译员。
    </small>
    <small v-if="!canRunTaskQualityComputed" class="permission-hint">
      当前身份无全量质检权限，请切换为质检员或项目负责人。
    </small>

    <template v-if="taskQualityResultRef">
      <div class="summary-grid">
        <span><small>检查覆盖</small><strong>{{ taskQualityResultRef.checked_plot_count }}/{{ taskQualityResultRef.total_plot_count }}</strong></span>
        <span><small>门禁通过</small><strong class="success">{{ taskQualityResultRef.passing_plot_count }}</strong></span>
        <span><small>需要整改</small><strong class="danger">{{ taskQualityResultRef.failed_plot_count }}</strong></span>
        <span><small>平均得分</small><strong>{{ taskQualityResultRef.average_score?.toFixed(1) || '--' }}</strong></span>
      </div>

      <div class="coverage-row">
        <span>覆盖率 {{ coveragePercentComputed }}%</span>
        <span>{{ taskQualityResultRef.issue_count }} 条规则问题</span>
        <span>耗时 {{ taskQualityResultRef.duration_ms }} ms</span>
      </div>
      <a-progress
        :percent="coveragePercentComputed"
        :show-info="false"
        :status="taskQualityResultRef.can_submit ? 'success' : 'exception'"
      />

      <div class="gate-state" :class="{ passed: taskQualityResultRef.can_submit }">
        <CheckCircleOutlined v-if="taskQualityResultRef.can_submit" />
        <span>
          <strong>{{ taskQualityResultRef.can_submit ? '满足提交门禁' : '存在阻断问题' }}</strong>
          <small>
            {{ taskQualityResultRef.can_submit
              ? '可提交至内业自检'
              : '请按规则汇总定位并整改图斑' }}
          </small>
        </span>
      </div>

      <div class="rule-summary-list">
        <div
          v-for="rule in taskQualityResultRef.rule_summaries"
          :key="rule.rule_code"
          :class="{ blocked: rule.blocking_issue_count > 0 }"
        >
          <span><strong>{{ rule.label }}</strong><small>{{ rule.rule_code }}</small></span>
          <span class="counts">
            <b class="pass">{{ rule.pass_count }}</b>
            <b v-if="rule.warning_count" class="warning">{{ rule.warning_count }}</b>
            <b v-if="rule.fail_count" class="fail">{{ rule.fail_count }}</b>
          </span>
        </div>
      </div>
    </template>

    <TaskQualityRunHistory />

    <a-collapse ghost class="issue-collapse">
      <a-collapse-panel key="issues" header="问题图斑队列 · 筛选与地图定位">
        <QualityIssueQueue />
      </a-collapse-panel>
    </a-collapse>
  </section>
</template>

<style scoped lang="less">
.task-quality-panel {
  padding: 12px;
  margin-bottom: 14px;
  background: #f6faf7;
  border: 1px solid #dce8e1;
  border-radius: 7px;
}

header,
.gate-state,
.coverage-row,
.rule-summary-list > div {
  display: flex;
  align-items: center;
}

header {
  gap: 8px;
}

header > span:nth-child(2) {
  display: flex;
  flex: 1;
  flex-direction: column;
}

.title-icon {
  display: grid;
  width: 28px;
  height: 28px;
  color: #2d6c4c;
  background: #e2efe7;
  border-radius: 6px;
  place-items: center;
}

header small,
.summary-grid small,
.gate-state small,
.rule-summary-list small {
  font-size: 8px;
  color: #849189;
}

header strong {
  font-size: 11px;
}

.description {
  margin: 9px 0;
  font-size: 8px;
  line-height: 15px;
  color: #65736b;
}

.submission-alert {
  margin-bottom: 8px;
  font-size: 9px;
}

.operator-row {
  display: grid;
  grid-template-columns: 0.8fr 1.2fr;
  gap: 6px;
}

.operator-identity {
  display: flex;
  align-items: center;
  padding: 0 8px;
  font-size: 8px;
  color: #506158;
  background: #f4f7f5;
  border: 1px solid #e0e7e3;
  border-radius: 4px;
}

.task-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 7px;
  margin-top: 8px;
}

.permission-hint {
  display: block;
  margin-top: 5px;
  font-size: 8px;
  color: #a06b2c;
}

.summary-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  margin-top: 10px;
}

.summary-grid > span {
  display: flex;
  flex-direction: column;
  padding: 7px;
  background: #fff;
  border: 1px solid #e2e9e5;
  border-radius: 5px;
}

.summary-grid strong {
  margin-top: 2px;
  font-size: 14px;
}

.summary-grid .success { color: #2f7a52; }
.summary-grid .danger { color: #c84a3d; }

.coverage-row {
  justify-content: space-between;
  margin-top: 9px;
  font-size: 7px;
  color: #748078;
}

.gate-state {
  gap: 7px;
  padding: 8px;
  margin-top: 8px;
  color: #b74336;
  background: #fff5f3;
  border: 1px solid #f0d6d1;
  border-radius: 5px;
}

.gate-state.passed {
  color: #2d7350;
  background: #f1f9f4;
  border-color: #d0e7d8;
}

.gate-state > span {
  display: flex;
  flex-direction: column;
}

.gate-state strong { font-size: 9px; }

.rule-summary-list {
  max-height: 230px;
  margin-top: 8px;
  overflow: auto;
  border-top: 1px solid #e2e9e5;
}

.rule-summary-list > div {
  justify-content: space-between;
  min-height: 38px;
  padding: 5px 2px;
  border-bottom: 1px dashed #e0e6e2;
}

.rule-summary-list > div.blocked { background: #fff8f6; }

.rule-summary-list > div > span:first-child {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.rule-summary-list strong { font-size: 8px; }

.counts {
  display: flex;
  gap: 4px;
}

.counts b {
  min-width: 22px;
  padding: 2px 4px;
  font-size: 7px;
  font-weight: 500;
  text-align: center;
  border-radius: 8px;
}

.counts .pass { color: #2e7550; background: #e6f3eb; }
.counts .warning { color: #9b6b10; background: #fff2cf; }
.counts .fail { color: #b84236; background: #fde8e5; }

.issue-collapse {
  margin-top: 8px;
  border-top: 1px solid #dfe7e2;
}

:deep(.issue-collapse .ant-collapse-header) {
  padding: 8px 0 !important;
  font-size: 8px;
  color: #315f48 !important;
}

:deep(.issue-collapse .ant-collapse-content-box) {
  padding: 0 !important;
}
</style>
