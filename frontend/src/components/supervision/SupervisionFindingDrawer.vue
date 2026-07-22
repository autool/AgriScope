<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

import type {
  SupervisionFinding,
  SupervisionRectificationPayload,
  SupervisionReinspectionPayload,
  SupervisionReinspectionResult,
} from '@/types/supervision'
import { supervisionFindingStatusLabels } from '@/types/supervision'

const props = defineProps<{
  finding: SupervisionFinding | null
  operatorCode: string | null
  canRectify: boolean
  canReinspect: boolean
  saving: boolean
}>()

const emit = defineEmits<{
  close: []
  rectify: [payload: SupervisionRectificationPayload]
  reinspect: [payload: SupervisionReinspectionPayload]
}>()

const activeTabRef = ref<'rectification' | 'reinspection'>('rectification')
const rectificationFormRef = reactive({ comment: '', evidenceUri: '' })
const reinspectionFormRef = reactive({
  result: 'passed' as SupervisionReinspectionResult,
  comment: '',
  evidenceUri: '',
})

const openComputed = computed<boolean>(() => props.finding !== null)
const canSubmitRectificationComputed = computed<boolean>(() => Boolean(
  props.finding
  && props.operatorCode
  && props.canRectify
  && ['open', 'rework_required'].includes(props.finding.status)
  && rectificationFormRef.comment.trim()
  && rectificationFormRef.evidenceUri.trim(),
))
const canSubmitReinspectionComputed = computed<boolean>(() => Boolean(
  props.finding
  && props.operatorCode
  && props.canReinspect
  && props.finding.status === 'rectification_submitted'
  && reinspectionFormRef.comment.trim()
  && reinspectionFormRef.evidenceUri.trim(),
))

watch(() => props.finding, (finding) => {
  activeTabRef.value = finding?.status === 'rectification_submitted'
    ? 'reinspection'
    : 'rectification'
})

const submitRectification = (): void => {
  if (!canSubmitRectificationComputed.value || !props.operatorCode) return
  emit('rectify', {
    rectification_comment: rectificationFormRef.comment.trim(),
    rectification_evidence_uri: rectificationFormRef.evidenceUri.trim(),
    operator_code: props.operatorCode,
  })
}

const submitReinspection = (): void => {
  if (!canSubmitReinspectionComputed.value || !props.operatorCode) return
  emit('reinspect', {
    result: reinspectionFormRef.result,
    comment: reinspectionFormRef.comment.trim(),
    evidence_uri: reinspectionFormRef.evidenceUri.trim(),
    operator_code: props.operatorCode,
  })
}
</script>

<template>
  <a-drawer
    :open="openComputed"
    width="620"
    title="监理问题闭环"
    @close="emit('close')"
  >
    <template v-if="finding">
      <section class="finding-summary">
        <header>
          <span><strong>{{ finding.finding_code }}</strong><small>{{ finding.region_name }} · {{ finding.plot_code || '县区级问题' }}</small></span>
          <a-tag :color="finding.status === 'closed' ? 'green' : finding.overdue ? 'red' : 'orange'">
            {{ supervisionFindingStatusLabels[finding.status] }}
          </a-tag>
        </header>
        <p>{{ finding.description }}</p>
        <dl>
          <div><dt>问题类型</dt><dd>{{ finding.issue_type }}</dd></div>
          <div><dt>严重度</dt><dd>{{ finding.severity }}</dd></div>
          <div><dt>整改期限</dt><dd>{{ finding.rework_deadline }}</dd></div>
          <div><dt>问题证据</dt><dd>{{ finding.evidence_uri }}</dd></div>
        </dl>
      </section>

      <a-tabs v-model:active-key="activeTabRef">
        <a-tab-pane key="rectification" tab="提交整改">
          <a-alert
            v-if="!canRectify"
            type="info"
            show-icon
            message="当前身份无整改提交能力"
            description="整改由内业、质检或项目负责人提交，独立监理不能代替生产团队整改。"
          />
          <a-alert
            v-else-if="!['open', 'rework_required'].includes(finding.status)"
            type="warning"
            show-icon
            message="当前状态不允许提交整改"
          />
          <a-form layout="vertical" class="action-form">
            <a-form-item label="整改证据地址" required>
              <a-input v-model:value="rectificationFormRef.evidenceUri" :disabled="!canSubmitRectificationComputed && !['open', 'rework_required'].includes(finding.status)" />
            </a-form-item>
            <a-form-item label="整改说明" required>
              <a-textarea v-model:value="rectificationFormRef.comment" :rows="4" />
            </a-form-item>
            <a-button
              type="primary"
              :loading="saving"
              :disabled="!canSubmitRectificationComputed"
              @click="submitRectification"
            >
              提交并等待独立复检
            </a-button>
          </a-form>
        </a-tab-pane>

        <a-tab-pane key="reinspection" tab="独立复检">
          <a-alert
            v-if="!canReinspect"
            type="info"
            show-icon
            message="仅独立监理可执行复检"
          />
          <a-alert
            v-else-if="finding.status !== 'rectification_submitted'"
            type="warning"
            show-icon
            message="生产团队尚未提交新的整改证据"
          />
          <a-form layout="vertical" class="action-form">
            <a-form-item label="复检结论" required>
              <a-radio-group v-model:value="reinspectionFormRef.result">
                <a-radio value="passed">通过并闭环</a-radio>
                <a-radio value="failed">未通过，继续整改</a-radio>
              </a-radio-group>
            </a-form-item>
            <a-form-item label="复检证据地址" required>
              <a-input v-model:value="reinspectionFormRef.evidenceUri" />
            </a-form-item>
            <a-form-item label="复检说明" required>
              <a-textarea v-model:value="reinspectionFormRef.comment" :rows="4" />
            </a-form-item>
            <a-button
              type="primary"
              :loading="saving"
              :disabled="!canSubmitReinspectionComputed"
              @click="submitReinspection"
            >
              保存第 {{ finding.reinspections.length + 1 }} 轮复检
            </a-button>
          </a-form>
        </a-tab-pane>

        <a-tab-pane key="history" tab="复检历史">
          <a-empty v-if="!finding.reinspections.length" description="尚无复检记录" />
          <a-timeline v-else>
            <a-timeline-item v-for="item in finding.reinspections" :key="item.round_no" :color="item.result === 'passed' ? 'green' : 'red'">
              <strong>第 {{ item.round_no }} 轮 · {{ item.result === 'passed' ? '通过' : '未通过' }}</strong>
              <p>{{ item.comment }}</p>
              <small>{{ item.inspector }} · {{ new Date(item.created_at).toLocaleString() }}</small>
            </a-timeline-item>
          </a-timeline>
        </a-tab-pane>
      </a-tabs>
    </template>
  </a-drawer>
</template>

<style scoped>
.finding-summary { padding: 12px; margin-bottom: 12px; background: #f7f9f8; border: 1px solid #e0e6e2; border-radius: 7px; }
.finding-summary header { display: flex; align-items: flex-start; justify-content: space-between; }
.finding-summary header span { display: flex; flex-direction: column; }
.finding-summary header small { margin-top: 2px; color: #7a8880; }
.finding-summary p { margin: 12px 0; color: #405048; }
.finding-summary dl { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin: 0; }
.finding-summary dl div { min-width: 0; padding: 7px; background: #fff; border-radius: 4px; }
.finding-summary dt { font-size: 10px; color: #849088; }
.finding-summary dd { margin: 2px 0 0; overflow-wrap: anywhere; font-size: 12px; }
.action-form { margin-top: 12px; }
</style>
