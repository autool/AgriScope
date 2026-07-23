<script setup lang="ts">
import {
  AuditOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons-vue'
import { storeToRefs } from 'pinia'
import { computed, onMounted } from 'vue'

import { useWorkbenchStore } from '@/store/workbenchStore'

const workbenchStore = useWorkbenchStore()
const {
  taskQualityRunsRef,
  taskQualityRunsLoadingRef,
} = storeToRefs(workbenchStore)

const runsComputed = computed(() => taskQualityRunsRef.value?.items || [])

const formatDateTime = (value: string): string => new Intl.DateTimeFormat(
  'zh-CN',
  {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  },
).format(new Date(value))

onMounted(() => {
  void workbenchStore.loadTaskQualityRuns().catch(() => undefined)
})
</script>

<template>
  <section class="quality-run-history">
    <header>
      <span><AuditOutlined /></span>
      <div>
        <small>IMMUTABLE QUALITY LEDGER</small>
        <strong>全量质检批次账本</strong>
      </div>
      <a-tag>{{ taskQualityRunsRef?.total_count || 0 }} 次运行</a-tag>
    </header>

    <a-spin :spinning="taskQualityRunsLoadingRef">
      <a-empty
        v-if="!taskQualityRunsLoadingRef && !runsComputed.length"
        description="尚无可复核的全量质检批次"
      />
      <a-collapse v-else ghost accordion>
        <a-collapse-panel
          v-for="run in runsComputed"
          :key="run.run_code"
        >
          <template #header>
            <span class="run-header">
              <component
                :is="run.can_submit ? CheckCircleOutlined : CloseCircleOutlined"
                :class="run.can_submit ? 'passed' : 'blocked'"
              />
              <span>
                <strong>{{ run.run_code }}</strong>
                <small>{{ formatDateTime(run.created_at) }} · {{ run.operator }} / {{ run.operator_role }}</small>
              </span>
              <span class="run-metrics">
                <b>{{ run.checked_plot_count.toLocaleString() }} 覆盖</b>
                <b>{{ run.passing_plot_count.toLocaleString() }} 通过</b>
                <b>{{ run.issue_count.toLocaleString() }} 问题</b>
                <b>{{ run.duration_ms.toLocaleString() }} ms</b>
              </span>
            </span>
          </template>

          <div class="snapshot-grid">
            <span><small>任务图斑快照</small><strong>{{ run.task_plot_count.toLocaleString() }}</strong></span>
            <span><small>平均得分</small><strong>{{ run.average_score?.toFixed(2) || '--' }}</strong></span>
            <span><small>规则配置版本</small><strong>v{{ run.rule_config_version }}</strong></span>
            <span><small>自定义字段模式</small><strong>{{ run.custom_field_schema_digest.slice(0, 12) }}</strong></span>
          </div>
          <p v-if="run.comment">{{ run.comment }}</p>
          <div class="rule-ledger">
            <span v-for="rule in run.rule_summaries" :key="rule.rule_code">
              <strong>{{ rule.label }}</strong>
              <small>{{ rule.rule_code }}</small>
              <em>
                通过 {{ rule.pass_count.toLocaleString() }} ·
                警告 {{ rule.warning_count.toLocaleString() }} ·
                失败 {{ rule.fail_count.toLocaleString() }}
              </em>
            </span>
          </div>
        </a-collapse-panel>
      </a-collapse>
    </a-spin>
  </section>
</template>

<style scoped lang="less">
.quality-run-history {
  padding: 10px;
  margin-top: 12px;
  background: #fff;
  border: 1px solid #dfe8e3;
  border-radius: 6px;
}

header,
.run-header,
.run-metrics {
  display: flex;
  align-items: center;
}

header {
  gap: 8px;
  padding: 0 4px 8px;
  border-bottom: 1px solid #edf1ef;
}

header > div {
  display: flex;
  flex: 1;
  flex-direction: column;
}

header small,
.run-header small,
.snapshot-grid small,
.rule-ledger small {
  font-size: 9px;
  color: #77857e;
}

.run-header {
  width: 100%;
  gap: 8px;
}

.run-header > span:nth-child(2) {
  display: flex;
  min-width: 230px;
  flex: 1;
  flex-direction: column;
}

.run-header > span:nth-child(2) strong {
  overflow-wrap: anywhere;
}

.run-metrics {
  gap: 10px;
  font-size: 9px;
  font-weight: normal;
  color: #506159;
}

.passed { color: #2f7a51; }
.blocked { color: #b94d4d; }

.snapshot-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 7px;
}

.snapshot-grid > span,
.rule-ledger > span {
  display: flex;
  flex-direction: column;
  padding: 8px;
  background: #f7faf8;
  border: 1px solid #e5ebe8;
  border-radius: 5px;
}

.quality-run-history p {
  padding: 7px 8px;
  margin: 8px 0;
  font-size: 10px;
  color: #506159;
  background: #f7faf8;
}

.rule-ledger {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  margin-top: 8px;
}

.rule-ledger em {
  margin-top: 3px;
  font-size: 9px;
  font-style: normal;
  color: #5f6f67;
}

@media (max-width: 900px) {
  .run-metrics { display: none; }
  .snapshot-grid, .rule-ledger { grid-template-columns: 1fr; }
}
</style>
