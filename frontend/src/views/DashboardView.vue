<script setup lang="ts">
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  MinusCircleOutlined,
} from '@ant-design/icons-vue'
import { storeToRefs } from 'pinia'
import { computed } from 'vue'

import { useWorkbenchStore } from '@/store/workbenchStore'

const workbenchStore = useWorkbenchStore()
const { overviewRef } = storeToRefs(workbenchStore)

const workflowStagesComputed = computed(() => overviewRef.value?.workflow.stages || [])
const workflowCompletedComputed = computed<boolean>(() => (
  workflowStagesComputed.value.length > 0
  && workflowStagesComputed.value.every((stage) => stage.status === 'completed')
))
const qualityDescriptionComputed = computed<string>(() => {
  const overview = overviewRef.value
  if (!overview?.task.quality_score) return '尚未形成任务质量得分'
  if (overview.statistics.open_issue_count > 0) {
    return `${overview.statistics.open_issue_count} 条问题待整改`
  }
  return '质量门禁已通过'
})

const statusLabel = (status: string): string => ({
  pending: '待开始',
  active: '进行中',
  blocked: '受阻',
  completed: '已完成',
  interpreting: '解译中',
  self_check: '内业自检',
  quality_review: '质检审核',
  client_review: '甲方复核',
  rejected: '已驳回',
})[status] || status

const statusColor = (status: string): string => ({
  completed: 'green',
  active: 'blue',
  blocked: 'red',
  pending: 'default',
  interpreting: 'blue',
  self_check: 'cyan',
  quality_review: 'gold',
  client_review: 'purple',
  rejected: 'red',
})[status] || 'default'
</script>

<template>
  <div class="dashboard-view">
    <section class="project-hero">
      <div>
        <small>PROVINCIAL MONITORING PROJECT</small>
        <h2>{{ overviewRef?.project?.project_name }}</h2>
        <p>{{ overviewRef?.project?.province }} · {{ overviewRef?.project?.monitor_year }} 年度常态化遥感监测</p>
      </div>
      <div class="progress-ring">
        <a-progress
          type="circle"
          :percent="overviewRef?.project?.progress ?? 0"
          :size="90"
          stroke-color="#74c99a"
        />
        <span>总体进度</span>
      </div>
    </section>

    <section class="metric-grid">
      <div><strong>{{ overviewRef?.statistics?.plot_count ?? 0 }}</strong><span>监测图斑</span><small>当前作业单元</small></div>
      <div><strong>{{ overviewRef?.statistics?.interpreted_count ?? 0 }}</strong><span>完成解译</span><small>属性已入库</small></div>
      <div><strong>{{ overviewRef?.task?.quality_score ?? '--' }}</strong><span>质量得分</span><small>{{ qualityDescriptionComputed }}</small></div>
      <div><strong>{{ overviewRef?.statistics?.review_record_count ?? 0 }}</strong><span>审计记录</span><small>全流程可追溯</small></div>
    </section>

    <div class="dashboard-grid">
      <section class="workflow-card">
        <header>
          <span><small>WORKFLOW</small><strong>监测业务流程</strong></span>
          <a-tag :color="workflowCompletedComputed ? 'green' : 'blue'">
            {{ workflowCompletedComputed ? '全流程完成' : `当前：${overviewRef?.workflow.current_stage || '加载中'}` }}
          </a-tag>
        </header>
        <div class="stage-list">
          <div v-for="(stage, index) in workflowStagesComputed" :key="stage.code" :class="stage.status">
            <i>
              <CheckCircleOutlined v-if="stage.status === 'completed'" />
              <ExclamationCircleOutlined v-else-if="stage.status === 'blocked'" />
              <ClockCircleOutlined v-else-if="stage.status === 'active'" />
              <MinusCircleOutlined v-else />
            </i>
            <span>
              <strong>{{ stage.label }} · {{ statusLabel(stage.status) }}</strong>
              <small>{{ stage.detail }}</small>
              <a-progress :percent="stage.progress" :show-info="false" size="small" />
            </span>
            <em>0{{ index + 1 }}</em>
          </div>
        </div>
      </section>

      <section class="task-card">
        <header><span><small>CURRENT TASK</small><strong>当前作业任务</strong></span></header>
        <h3>{{ overviewRef?.task?.task_name }}</h3>
        <p>{{ overviewRef?.task?.administrative_region }} · 负责人 {{ overviewRef?.task?.assignee }}</p>
        <dl>
          <div><dt>任务编号</dt><dd>{{ overviewRef?.task?.task_code }}</dd></div>
          <div><dt>审核状态</dt><dd><a-tag :color="statusColor(overviewRef?.task?.status || '')">{{ statusLabel(overviewRef?.task?.status || '') }}</a-tag></dd></div>
          <div><dt>计划图斑</dt><dd>{{ overviewRef?.task?.total_plots }}</dd></div>
          <div><dt>截止日期</dt><dd>{{ overviewRef?.task?.deadline }}</dd></div>
        </dl>
      </section>
    </div>
  </div>
</template>

<style scoped>
.dashboard-view { height: 100%; padding: 14px; overflow: auto; }
.project-hero { display: flex; align-items: center; justify-content: space-between; padding: 22px 28px; color: #fff; background: linear-gradient(125deg, #204b37, #438d65); border-radius: 9px; }
.project-hero small { font-size: 8px; color: rgb(255 255 255 / 55%); letter-spacing: 1px; }
.project-hero h2 { margin: 7px 0; color: #fff; font-size: 22px; }
.project-hero p { margin: 0; font-size: 10px; color: rgb(255 255 255 / 70%); }
.progress-ring { display: flex; flex-direction: column; align-items: center; gap: 4px; font-size: 8px; }
.metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 11px 0; }
.metric-grid > div { padding: 16px; background: #fff; border: 1px solid #dfe6e2; border-radius: 7px; }
.metric-grid strong, .metric-grid span, .metric-grid small { display: block; }
.metric-grid strong { font-size: 27px; color: #337b56; }
.metric-grid span { font-size: 10px; font-weight: 600; }
.metric-grid small { margin-top: 3px; font-size: 8px; color: #8b9690; }
.dashboard-grid { display: grid; grid-template-columns: 1.4fr 1fr; gap: 10px; }
.workflow-card, .task-card { padding: 16px; background: #fff; border: 1px solid #dfe6e2; border-radius: 7px; }
header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
header > span { display: flex; flex-direction: column; }
header small { font-size: 7px; color: #91a099; }
header strong { font-size: 11px; }
.stage-list { display: grid; grid-template-columns: repeat(2, 1fr); gap: 7px; }
.stage-list > div { display: grid; grid-template-columns: 28px 1fr auto; gap: 8px; align-items: center; padding: 10px; background: #f6f8f7; border-radius: 5px; }
.stage-list i { display: grid; width: 27px; height: 27px; color: #fff; background: #4a9c70; border-radius: 50%; place-items: center; }
.stage-list .active i { background: #d9953d; }
.stage-list .blocked i { background: #cf584d; }
.stage-list .pending i { color: #87938c; background: #e4e9e6; }
.stage-list span { display: flex; flex-direction: column; }
.stage-list strong { font-size: 9px; }
.stage-list small { min-height: 20px; font-size: 7px; color: #8b9690; }
.stage-list :deep(.ant-progress) { margin: 3px 0 0; line-height: 1; }
.stage-list em { font-size: 8px; font-style: normal; color: #9aa59f; }
.task-card h3 { margin: 16px 0 4px; font-size: 16px; }
.task-card > p { font-size: 9px; color: #7d8983; }
.task-card dl { margin: 15px 0 0; }
.task-card dl > div { display: flex; justify-content: space-between; padding: 9px 0; font-size: 9px; border-bottom: 1px solid #edf0ee; }
.task-card dt { color: #7c8982; }
.task-card dd { margin: 0; font-weight: 600; }
</style>
