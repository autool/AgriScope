<script setup lang="ts">
import { computed } from 'vue'

import type {
  SupervisionFinding,
  SupervisionInspection,
  SupervisionPlan,
} from '@/types/supervision'
import {
  supervisionFindingStatusLabels,
  supervisionSamplingMethodLabels,
  supervisionStageLabels,
} from '@/types/supervision'

const props = defineProps<{
  plan: SupervisionPlan
  canSupervise: boolean
  canRectify: boolean
  reportDownloadUrl: string | undefined
  saving: boolean
}>()

const emit = defineEmits<{
  createInspection: []
  createFinding: [inspection: SupervisionInspection]
  openFinding: [finding: SupervisionFinding]
  viewSamples: []
  evaluateCounty: []
  generateReport: []
}>()

const findingsComputed = computed<SupervisionFinding[]>(() => (
  props.plan.inspections.flatMap((inspection) => inspection.findings)
))

const reportGateComputed = computed<{ ready: boolean, reasons: string[] }>(() => {
  const reasons: string[] = []
  if (!props.plan.inspection_count) reasons.push('至少登记一次过程检查')
  if (props.plan.open_finding_count) reasons.push(`闭环 ${props.plan.open_finding_count} 个问题`)
  if (props.plan.evaluation_count < Object.keys(props.plan.region_sample_counts).length) {
    reasons.push('完成全部抽样县区评价')
  }
  return { ready: !reasons.length && props.plan.status === 'active', reasons }
})

const conclusionColor = (conclusion: string): string => ({
  passed: 'green',
  conditional: 'orange',
  failed: 'red',
}[conclusion] || 'default')

const findingColor = (finding: SupervisionFinding): string => {
  if (finding.status === 'closed') return 'green'
  if (finding.overdue || finding.severity === 'critical') return 'red'
  return 'orange'
}

const findingStatusLabel = (finding: SupervisionFinding): string => (
  supervisionFindingStatusLabels[finding.status]
)
</script>

<template>
  <section class="plan-workspace">
    <header class="plan-header">
      <span>
        <strong>{{ plan.plan_name }}</strong>
        <small>{{ plan.plan_code }} · {{ supervisionSamplingMethodLabels[plan.sampling_method] }} · {{ plan.sample_ratio }}%</small>
      </span>
      <div>
        <a-tag :color="plan.status === 'completed' ? 'green' : 'blue'">{{ plan.status === 'completed' ? '已形成报告' : '执行中' }}</a-tag>
        <a-button @click="emit('viewSamples')">查看 {{ plan.sample_count.toLocaleString() }} 个样本</a-button>
        <a-button v-if="canSupervise" :disabled="plan.status !== 'active'" @click="emit('createInspection')">登记检查</a-button>
        <a-button v-if="canSupervise" :disabled="plan.status !== 'active'" @click="emit('evaluateCounty')">县区评价</a-button>
      </div>
    </header>

    <div class="plan-facts">
      <article><strong>{{ plan.region_codes.length }}</strong><small>抽样县区</small></article>
      <article><strong>{{ plan.sample_count.toLocaleString() }}</strong><small>显式样本</small></article>
      <article><strong>{{ plan.inspection_count }}</strong><small>过程检查</small></article>
      <article :class="{ warning: plan.open_finding_count > 0 }"><strong>{{ plan.open_finding_count }}</strong><small>未闭环问题</small></article>
      <article :class="{ warning: plan.overdue_finding_count > 0 }"><strong>{{ plan.overdue_finding_count }}</strong><small>逾期问题</small></article>
      <article><strong>{{ plan.evaluation_count }} / {{ Object.keys(plan.region_sample_counts).length }}</strong><small>县区评价</small></article>
    </div>

    <a-alert
      class="snapshot-alert"
      type="info"
      show-icon
      :message="`任务快照：${plan.task_plot_count_snapshot.toLocaleString()} 个图斑 · ${new Date(plan.task_updated_at_snapshot).toLocaleString()}`"
      description="样本和报告均绑定该数据版本；任务图斑范围或更新时间变化后，服务端会拒绝继续追加证据。"
    />

    <a-tabs>
      <a-tab-pane key="inspections" tab="过程检查">
        <a-empty v-if="!plan.inspections.length" description="尚未登记独立过程检查" />
        <a-collapse v-else accordion>
          <a-collapse-panel
            v-for="inspection in plan.inspections"
            :key="inspection.inspection_code"
          >
            <template #header>
              <div class="inspection-title">
                <span><strong>{{ inspection.inspection_code }}</strong><small>{{ supervisionStageLabels[inspection.inspection_stage] }} · {{ new Date(inspection.inspected_at).toLocaleString() }}</small></span>
                <a-tag :color="conclusionColor(inspection.conclusion)">{{ inspection.conclusion }}</a-tag>
                <em>{{ inspection.findings.length }} 个问题</em>
              </div>
            </template>
            <p class="inspection-summary">{{ inspection.summary }}</p>
            <div class="inspection-meta">证据：{{ inspection.evidence_uri }} · 检查人：{{ inspection.inspector }}</div>
            <a-button v-if="canSupervise && plan.status === 'active'" size="small" @click="emit('createFinding', inspection)">登记问题</a-button>
          </a-collapse-panel>
        </a-collapse>
      </a-tab-pane>

      <a-tab-pane key="findings">
        <template #tab>问题闭环 <a-badge :count="plan.open_finding_count" /></template>
        <a-empty v-if="!findingsComputed.length" description="当前检查未登记监理问题" />
        <a-table
          v-else
          size="small"
          row-key="finding_code"
          :data-source="findingsComputed"
          :pagination="{ pageSize: 10 }"
        >
          <a-table-column key="finding" title="问题">
            <template #default="{ record }">
              <span class="finding-cell"><strong>{{ record.finding_code }}</strong><small>{{ record.issue_type }} · {{ record.plot_code || record.region_name }}</small></span>
            </template>
          </a-table-column>
          <a-table-column title="严重度" data-index="severity" width="90" />
          <a-table-column title="整改期限" width="120">
            <template #default="{ record }"><span :class="{ overdue: record.overdue }">{{ record.rework_deadline }}</span></template>
          </a-table-column>
          <a-table-column title="状态" width="120">
            <template #default="{ record }"><a-tag :color="findingColor(record)">{{ findingStatusLabel(record) }}</a-tag></template>
          </a-table-column>
          <a-table-column title="复检" width="80">
            <template #default="{ record }">{{ record.reinspections.length }} 轮</template>
          </a-table-column>
          <a-table-column title="操作" width="110">
            <template #default="{ record }">
              <a-button type="link" size="small" @click="emit('openFinding', record)">{{ canRectify || canSupervise ? '处理' : '查看' }}</a-button>
            </template>
          </a-table-column>
        </a-table>
      </a-tab-pane>

      <a-tab-pane key="evaluations" tab="县区评价">
        <a-empty v-if="!plan.county_evaluations.length" description="尚未提交县区监理评价" />
        <div v-else class="evaluation-grid">
          <article v-for="item in plan.county_evaluations" :key="item.region_code">
            <header><span><strong>{{ item.region_name }}</strong><small>{{ item.region_code }}</small></span><b>{{ item.grade }}</b></header>
            <div><em>综合</em><strong>{{ item.overall_score }}</strong></div>
            <small>质量 {{ item.quality_score }} · 时效 {{ item.timeliness_score }} · 合规 {{ item.compliance_score }}</small>
            <p>{{ item.comment }}</p>
          </article>
        </div>
      </a-tab-pane>

      <a-tab-pane key="events" tab="审计事件">
        <a-empty v-if="!plan.recent_events.length" description="暂无监理审计事件" />
        <a-timeline v-else>
          <a-timeline-item v-for="event in plan.recent_events" :key="`${event.entity_type}-${event.entity_code}-${event.created_at}`">
            <strong>{{ event.action }} · {{ event.entity_code }}</strong>
            <p>{{ event.comment }}</p>
            <small>{{ event.operator }}（{{ event.operator_role }}）· {{ new Date(event.created_at).toLocaleString() }}</small>
          </a-timeline-item>
        </a-timeline>
      </a-tab-pane>

      <a-tab-pane key="report" tab="监理报告">
        <div v-if="plan.report" class="report-card">
          <span><strong>{{ plan.report.report_code }}</strong><small>SHA-256：{{ plan.report.checksum_sha256 }}</small><em>{{ plan.report.file_size_bytes.toLocaleString() }} bytes · {{ new Date(plan.report.generated_at).toLocaleString() }}</em></span>
          <a-button type="primary" :href="reportDownloadUrl" :disabled="!reportDownloadUrl">下载并复核实体报告</a-button>
        </div>
        <div v-else class="report-gate">
          <a-result :status="reportGateComputed.ready ? 'success' : 'info'" :title="reportGateComputed.ready ? '监理证据已满足报告门禁' : '监理报告尚未具备生成条件'">
            <template #subTitle>
              <span v-if="reportGateComputed.ready">生成后计划将冻结，报告文件包含样本、检查、问题、复检、县区评价和完整事件证据。</span>
              <span v-else>{{ reportGateComputed.reasons.join('；') }}</span>
            </template>
            <template #extra>
              <a-button
                type="primary"
                :loading="saving"
                :disabled="!canSupervise || !reportGateComputed.ready"
                @click="emit('generateReport')"
              >
                生成不可变监理报告
              </a-button>
            </template>
          </a-result>
        </div>
      </a-tab-pane>
    </a-tabs>
  </section>
</template>

<style scoped>
.plan-workspace { padding: 14px; background: #fff; border: 1px solid #dfe6e2; border-radius: 8px; }
.plan-header, .plan-header > div, .inspection-title, .report-card { display: flex; align-items: center; }
.plan-header { justify-content: space-between; gap: 12px; }
.plan-header > span, .finding-cell, .inspection-title > span, .report-card > span { display: flex; flex-direction: column; min-width: 0; }
.plan-header > span strong { font-size: 15px; }
.plan-header small, .finding-cell small, .inspection-title small, .report-card small, .report-card em { color: #7d8a83; }
.plan-header > div { gap: 7px; flex-wrap: wrap; }
.plan-facts { display: grid; grid-template-columns: repeat(6, 1fr); gap: 7px; margin: 12px 0; }
.plan-facts article { display: flex; flex-direction: column; padding: 9px; background: #f7f9f8; border: 1px solid #e2e7e4; border-radius: 6px; }
.plan-facts article.warning { color: #c15c43; background: #fff8f5; border-color: #efd4ca; }
.plan-facts strong { font-size: 16px; }
.plan-facts small { color: #748179; }
.snapshot-alert { margin-bottom: 10px; }
.inspection-title { width: 100%; gap: 12px; }
.inspection-title > span { flex: 1; }
.inspection-title em { min-width: 70px; font-style: normal; color: #748179; text-align: right; }
.inspection-summary { margin: 0 0 7px; }
.inspection-meta { margin-bottom: 10px; font-size: 11px; color: #77847d; overflow-wrap: anywhere; }
.overdue { font-weight: 600; color: #c04f3b; }
.evaluation-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.evaluation-grid article { padding: 11px; background: #f8faf9; border: 1px solid #e0e6e2; border-radius: 7px; }
.evaluation-grid article header { display: flex; align-items: center; justify-content: space-between; }
.evaluation-grid article header span { display: flex; flex-direction: column; }
.evaluation-grid article header b { font-size: 22px; color: #3f805e; }
.evaluation-grid article > div { display: flex; align-items: baseline; gap: 5px; margin-top: 8px; }
.evaluation-grid article > div strong { font-size: 20px; }
.evaluation-grid article p { margin: 8px 0 0; color: #526158; }
.report-card { justify-content: space-between; gap: 14px; padding: 14px; background: #f5faf7; border: 1px solid #d7e8dd; border-radius: 7px; }
.report-card em { margin-top: 3px; font-style: normal; }
@media (max-width: 1180px) { .plan-facts { grid-template-columns: repeat(3, 1fr); } .evaluation-grid { grid-template-columns: 1fr 1fr; } }
</style>
