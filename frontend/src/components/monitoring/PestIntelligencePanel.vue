<script setup lang="ts">
import { message } from 'ant-design-vue'
import { ref } from 'vue'

import type {
  AlertCreatePayload,
  AssessmentCreatePayload,
  MonitoringDevice,
  PestAlert,
  PestAssessment,
  PestModelCreatePayload,
  PestModelVersion,
  RiskLevel,
} from '@/types/monitoringNetwork'

defineProps<{
  models: PestModelVersion[]
  assessments: PestAssessment[]
  alerts: PestAlert[]
  devices: MonitoringDevice[]
  canManageModels: boolean
  canIngest: boolean
  canReview: boolean
  canDeliverAlert: boolean
  loading: boolean
}>()

const emit = defineEmits<{
  'register-model': [payload: Omit<PestModelCreatePayload, 'operator_code'>]
  'submit-assessment': [payload: Omit<AssessmentCreatePayload, 'operator_code'>]
  'review-assessment': [assessmentCode: string, decision: 'approve' | 'reject', comment: string]
  'create-alert': [assessmentCode: string, payload: Omit<AlertCreatePayload, 'operator_code'>]
  'deliver-alert': [alertCode: string, receiptUri: string, receiptSize: number, receiptSha: string]
}>()

const modelModalOpenRef = ref<boolean>(false)
const assessmentModalOpenRef = ref<boolean>(false)
const alertModalOpenRef = ref<boolean>(false)
const deliveryModalOpenRef = ref<boolean>(false)
const reviewModalOpenRef = ref<boolean>(false)
const targetAssessmentRef = ref<PestAssessment | null>(null)
const reviewDecisionRef = ref<'approve' | 'reject'>('approve')
const reviewCommentRef = ref<string>('')
const targetAlertRef = ref<PestAlert | null>(null)

const modelCodeRef = ref<string>('')
const modelVersionRef = ref<string>('')
const modelNameRef = ref<string>('')
const targetTypeRef = ref<'pest' | 'disease'>('pest')
const deploymentTargetRef = ref<string>('')
const trainingSourceRef = ref<string>('')
const evaluationSourceRef = ref<string>('')
const artifactUriRef = ref<string>('')
const artifactSizeRef = ref<number | null>(null)
const artifactShaRef = ref<string>('')
const accuracyRef = ref<number | null>(null)
const recallRef = ref<number | null>(null)
const f1Ref = ref<number | null>(null)
const rocRef = ref<number | null>(null)

const assessmentCodeRef = ref<string>('')
const assessmentDeviceRef = ref<string | undefined>(undefined)
const assessmentModelKeyRef = ref<string>('')
const assessmentObservedAtRef = ref<string>('')
const inputUriRef = ref<string>('')
const inputSizeRef = ref<number | null>(null)
const inputShaRef = ref<string>('')
const inputSummaryRef = ref<string>('{}')
const targetNameRef = ref<string>('')
const predictionLabelRef = ref<string>('')
const confidenceRef = ref<number | null>(null)
const predictionBasisRef = ref<string>('')

const alertCodeRef = ref<string>('')
const riskLevelRef = ref<RiskLevel>('high')
const alertMessageRef = ref<string>('')
const channelsRef = ref<Array<'platform' | 'sms' | 'email' | 'mobile'>>(['platform'])
const recipientsRef = ref<string>('')
const receiptUriRef = ref<string>('')
const receiptSizeRef = ref<number | null>(null)
const receiptShaRef = ref<string>('')

const submitModel = (): void => {
  if (
    !modelCodeRef.value || !modelVersionRef.value || !modelNameRef.value
    || !deploymentTargetRef.value || !trainingSourceRef.value || !evaluationSourceRef.value
    || !artifactUriRef.value || !artifactSizeRef.value || artifactShaRef.value.length !== 64
    || accuracyRef.value === null || recallRef.value === null
    || f1Ref.value === null || rocRef.value === null
  ) {
    message.warning('请完整填写模型来源、实体 SHA-256 和四项 0–1 评估指标')
    return
  }
  emit('register-model', {
    model_code: modelCodeRef.value.trim(),
    model_version: modelVersionRef.value.trim(),
    model_name: modelNameRef.value.trim(),
    target_type: targetTypeRef.value,
    deployment_target: deploymentTargetRef.value.trim(),
    training_source_uri: trainingSourceRef.value.trim(),
    evaluation_source_uri: evaluationSourceRef.value.trim(),
    artifact_uri: artifactUriRef.value.trim(),
    artifact_size_bytes: artifactSizeRef.value,
    artifact_sha256: artifactShaRef.value.trim(),
    accuracy: accuracyRef.value,
    recall: recallRef.value,
    f1_score: f1Ref.value,
    roc_auc: rocRef.value,
  })
  modelModalOpenRef.value = false
}

const submitAssessment = (): void => {
  const [modelCode, modelVersion] = assessmentModelKeyRef.value.split(':')
  if (
    !assessmentCodeRef.value || !modelCode || !modelVersion || !assessmentObservedAtRef.value
    || !inputUriRef.value || !inputSizeRef.value || inputShaRef.value.length !== 64
    || !targetNameRef.value || !predictionLabelRef.value || confidenceRef.value === null
    || !predictionBasisRef.value
  ) {
    message.warning('请完整填写模型版本、输入实体、预测结果和依据')
    return
  }
  let inputSummary: Record<string, unknown>
  try {
    inputSummary = JSON.parse(inputSummaryRef.value) as Record<string, unknown>
  } catch {
    message.warning('输入摘要必须是合法 JSON 对象')
    return
  }
  emit('submit-assessment', {
    assessment_code: assessmentCodeRef.value.trim(),
    ...(assessmentDeviceRef.value ? { device_code: assessmentDeviceRef.value } : {}),
    model_code: modelCode,
    model_version: modelVersion,
    observed_at: assessmentObservedAtRef.value.trim(),
    input_uri: inputUriRef.value.trim(),
    input_size_bytes: inputSizeRef.value,
    input_sha256: inputShaRef.value.trim(),
    input_summary: inputSummary,
    target_name: targetNameRef.value.trim(),
    prediction_label: predictionLabelRef.value.trim(),
    confidence: confidenceRef.value,
    prediction_basis: predictionBasisRef.value.trim(),
  })
  assessmentModalOpenRef.value = false
}

const review = (assessment: PestAssessment, decision: 'approve' | 'reject'): void => {
  targetAssessmentRef.value = assessment
  reviewDecisionRef.value = decision
  reviewCommentRef.value = ''
  reviewModalOpenRef.value = true
}

const submitReview = (): void => {
  if (!targetAssessmentRef.value || reviewCommentRef.value.trim().length < 4) {
    message.warning('复核依据至少填写 4 个字符')
    return
  }
  emit(
    'review-assessment',
    targetAssessmentRef.value.assessment_code,
    reviewDecisionRef.value,
    reviewCommentRef.value.trim(),
  )
  reviewModalOpenRef.value = false
}

const openAlert = (assessment: PestAssessment): void => {
  targetAssessmentRef.value = assessment
  alertModalOpenRef.value = true
}

const submitAlert = (): void => {
  if (!targetAssessmentRef.value || !alertCodeRef.value || !alertMessageRef.value) {
    message.warning('请填写告警编号和告警正文')
    return
  }
  const recipients = recipientsRef.value.split(/[，,\n]/).map(item => item.trim()).filter(Boolean)
  if (!recipients.length) {
    message.warning('至少填写一个真实接收对象')
    return
  }
  emit('create-alert', targetAssessmentRef.value.assessment_code, {
    alert_code: alertCodeRef.value.trim(),
    risk_level: riskLevelRef.value,
    message: alertMessageRef.value.trim(),
    channels: channelsRef.value,
    recipients,
  })
  alertModalOpenRef.value = false
}

const openDelivery = (alert: PestAlert): void => {
  targetAlertRef.value = alert
  deliveryModalOpenRef.value = true
}

const submitDelivery = (): void => {
  if (
    !targetAlertRef.value || !receiptUriRef.value || !receiptSizeRef.value
    || receiptShaRef.value.length !== 64
  ) {
    message.warning('请完整填写送达回执 URI、大小和 64 位 SHA-256')
    return
  }
  emit('deliver-alert', targetAlertRef.value.alert_code, receiptUriRef.value.trim(), receiptSizeRef.value, receiptShaRef.value.trim())
  deliveryModalOpenRef.value = false
}
</script>

<template>
  <section class="pest-panel">
    <header>
      <div><small>MODEL REVIEW & ALERTING</small><h3>病虫害模型复核与告警</h3></div>
      <a-space>
        <a-button size="small" :disabled="!canManageModels" @click="modelModalOpenRef = true">登记模型</a-button>
        <a-button
          size="small"
          type="primary"
          :disabled="!canIngest || !models.some(item => item.status === 'active')"
          @click="assessmentModalOpenRef = true"
        >
          提交识别
        </a-button>
      </a-space>
    </header>
    <div class="model-strip">
      <span><strong>{{ models.filter(item => item.status === 'active').length }}</strong><em>活动模型</em></span>
      <span><strong>{{ assessments.filter(item => item.status === 'pending_review').length }}</strong><em>待人工复核</em></span>
      <span><strong>{{ alerts.filter(item => item.status === 'pending').length }}</strong><em>待登记送达</em></span>
    </div>
    <div class="queue">
      <div class="section-title">识别复核队列</div>
      <article v-for="assessment in assessments" :key="assessment.assessment_code" class="assessment-card">
        <div class="card-heading"><span><strong>{{ assessment.target_name }} · {{ assessment.prediction_label }}</strong><em>{{ assessment.assessment_code }} · {{ assessment.model_code }} {{ assessment.model_version }}</em></span><a-tag :color="assessment.status === 'approved' ? 'green' : assessment.status === 'rejected' ? 'red' : 'orange'">{{ assessment.status }}</a-tag></div>
        <p>{{ assessment.prediction_basis }}</p>
        <div class="evidence-row"><span>置信度 {{ (assessment.confidence * 100).toFixed(1) }}%</span><span>输入 SHA {{ assessment.input_sha256.slice(0, 10) }}…</span></div>
        <footer>
          <a-space v-if="assessment.status === 'pending_review'">
            <a-button size="small" :disabled="!canReview" @click="review(assessment, 'reject')">驳回</a-button>
            <a-button
              size="small"
              type="primary"
              :disabled="!canReview"
              @click="review(assessment, 'approve')"
            >
              批准
            </a-button>
          </a-space>
          <a-button
            v-else-if="assessment.status === 'approved' && !alerts.some(item => item.assessment_code === assessment.assessment_code)"
            size="small"
            type="primary"
            :disabled="!canDeliverAlert"
            @click="openAlert(assessment)"
          >
            创建告警
          </a-button>
          <span v-else>{{ assessment.review_comment || '已完成业务处理' }}</span>
        </footer>
      </article>
      <a-empty v-if="!assessments.length" description="尚无模型识别结果；不会展示固定告警" />

      <div class="section-title">告警送达队列</div>
      <article v-for="alert in alerts" :key="alert.alert_code" class="alert-card">
        <div class="card-heading"><span><strong>{{ alert.alert_code }} · {{ alert.risk_level }}</strong><em>{{ alert.channels.join(' / ') }} → {{ alert.recipients.join('、') }}</em></span><a-tag :color="alert.status === 'delivered' ? 'green' : 'orange'">{{ alert.status }}</a-tag></div>
        <p>{{ alert.message }}</p>
        <footer>
          <span>{{ alert.delivery_receipt_sha256 ? `回执 ${alert.delivery_receipt_sha256.slice(0, 10)}…` : '等待真实送达回执' }}</span><a-button
            v-if="alert.status === 'pending'"
            size="small"
            type="primary"
            :disabled="!canDeliverAlert"
            @click="openDelivery(alert)"
          >
            登记送达
          </a-button>
        </footer>
      </article>
    </div>

    <a-modal
      v-model:open="modelModalOpenRef"
      title="登记病虫害模型实体版本"
      :confirm-loading="loading"
      width="760px"
      @ok="submitModel"
    >
      <div class="form-grid">
        <label><span>模型编码</span><a-input v-model:value="modelCodeRef" /></label><label><span>模型版本</span><a-input v-model:value="modelVersionRef" /></label>
        <label><span>模型名称</span><a-input v-model:value="modelNameRef" /></label><label><span>识别类型</span><a-select v-model:value="targetTypeRef" :options="[{ value: 'pest', label: '虫害' }, { value: 'disease', label: '病害' }]" /></label>
        <label class="wide"><span>部署目标</span><a-input v-model:value="deploymentTargetRef" placeholder="服务端、边缘设备或移动端" /></label>
        <label class="wide"><span>训练数据来源</span><a-input v-model:value="trainingSourceRef" /></label><label class="wide"><span>评估数据来源</span><a-input v-model:value="evaluationSourceRef" /></label>
        <label class="wide"><span>模型实体 URI</span><a-input v-model:value="artifactUriRef" /></label><label><span>实体大小（字节）</span><a-input-number v-model:value="artifactSizeRef" :min="1" /></label><label><span>实体 SHA-256</span><a-input v-model:value="artifactShaRef" :maxlength="64" /></label>
        <label><span>Accuracy</span><a-input-number
          v-model:value="accuracyRef"
          :min="0"
          :max="1"
          :step="0.01"
        /></label><label><span>Recall</span><a-input-number
          v-model:value="recallRef"
          :min="0"
          :max="1"
          :step="0.01"
        /></label><label><span>F1</span><a-input-number
          v-model:value="f1Ref"
          :min="0"
          :max="1"
          :step="0.01"
        /></label><label><span>ROC AUC</span><a-input-number
          v-model:value="rocRef"
          :min="0"
          :max="1"
          :step="0.01"
        /></label>
      </div>
    </a-modal>

    <a-modal
      v-model:open="assessmentModalOpenRef"
      title="提交模型识别结果"
      :confirm-loading="loading"
      width="760px"
      @ok="submitAssessment"
    >
      <div class="form-grid">
        <label><span>识别编号</span><a-input v-model:value="assessmentCodeRef" /></label><label><span>关联设备（可选）</span><a-select v-model:value="assessmentDeviceRef" allow-clear :options="devices.map(item => ({ value: item.device_code, label: `${item.device_name} · ${item.device_code}` }))" /></label>
        <label><span>活动模型版本</span><a-select v-model:value="assessmentModelKeyRef" :options="models.filter(item => item.status === 'active').map(item => ({ value: `${item.model_code}:${item.model_version}`, label: `${item.model_name} · ${item.model_version}` }))" /></label><label><span>观测时间</span><a-input v-model:value="assessmentObservedAtRef" placeholder="ISO 8601，必须包含时区" /></label>
        <label class="wide"><span>输入实体 URI</span><a-input v-model:value="inputUriRef" /></label><label><span>输入大小（字节）</span><a-input-number v-model:value="inputSizeRef" :min="1" /></label><label><span>输入 SHA-256</span><a-input v-model:value="inputShaRef" :maxlength="64" /></label>
        <label class="wide"><span>输入摘要 JSON</span><a-textarea v-model:value="inputSummaryRef" :rows="2" /></label><label><span>目标名称</span><a-input v-model:value="targetNameRef" /></label><label><span>预测标签</span><a-input v-model:value="predictionLabelRef" /></label><label><span>置信度</span><a-input-number
          v-model:value="confidenceRef"
          :min="0"
          :max="1"
          :step="0.01"
        /></label>
        <label class="wide"><span>预测依据</span><a-textarea v-model:value="predictionBasisRef" :rows="3" /></label>
      </div>
    </a-modal>

    <a-modal
      v-model:open="alertModalOpenRef"
      title="创建待发送病虫害告警"
      :confirm-loading="loading"
      @ok="submitAlert"
    >
      <div class="form-grid">
        <label><span>告警编号</span><a-input v-model:value="alertCodeRef" /></label><label><span>风险级别</span><a-select v-model:value="riskLevelRef" :options="[{ value: 'low', label: '低' }, { value: 'medium', label: '中' }, { value: 'high', label: '高' }, { value: 'critical', label: '紧急' }]" /></label>
        <label class="wide"><span>发送渠道</span><a-checkbox-group v-model:value="channelsRef" :options="[{ value: 'platform', label: '平台' }, { value: 'sms', label: '短信' }, { value: 'email', label: '邮件' }, { value: 'mobile', label: '移动端' }]" /></label>
        <label class="wide"><span>真实接收对象</span><a-textarea v-model:value="recipientsRef" :rows="2" placeholder="逗号或换行分隔" /></label><label class="wide"><span>告警正文</span><a-textarea v-model:value="alertMessageRef" :rows="4" /></label>
      </div>
    </a-modal>

    <a-modal
      v-model:open="deliveryModalOpenRef"
      title="登记告警真实送达回执"
      :confirm-loading="loading"
      @ok="submitDelivery"
    >
      <div class="form-grid"><label class="wide"><span>回执 URI</span><a-input v-model:value="receiptUriRef" /></label><label><span>回执大小（字节）</span><a-input-number v-model:value="receiptSizeRef" :min="1" /></label><label><span>回执 SHA-256</span><a-input v-model:value="receiptShaRef" :maxlength="64" /></label></div>
    </a-modal>

    <a-modal
      v-model:open="reviewModalOpenRef"
      :title="reviewDecisionRef === 'approve' ? '批准模型识别结果' : '驳回模型识别结果'"
      :confirm-loading="loading"
      @ok="submitReview"
    >
      <label><span>人工判读、现场证据或专家复核依据</span><a-textarea v-model:value="reviewCommentRef" :rows="4" /></label>
    </a-modal>
  </section>
</template>

<style scoped>
.pest-panel { display: flex; flex-direction: column; min-height: 0; padding: 12px; overflow: hidden; background: #fff; border: 1px solid #dfe5e2; border-radius: 8px; }
header, .card-heading, article footer, .evidence-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
header { margin-bottom: 9px; } small { font-size: 8px; color: #718078; letter-spacing: 1px; } h3 { margin: 2px 0 0; font-size: 15px; color: #20352c; }
.model-strip { display: grid; grid-template-columns: repeat(3, 1fr); gap: 5px; }
.model-strip span { display: flex; flex-direction: column; padding: 7px; background: #f3f7f5; border-radius: 6px; } .model-strip strong { font-size: 16px; color: #347958; } .model-strip em { font-size: 8px; font-style: normal; color: #7d8c84; }
.queue { flex: 1; min-height: 0; padding-top: 8px; overflow: auto; } .section-title { padding: 8px 2px 5px; font-size: 10px; color: #5d6e65; border-bottom: 1px solid #e6ebe8; }
article { padding: 8px; margin-top: 6px; border: 1px solid #e2e7e4; border-radius: 6px; } .assessment-card { border-left: 3px solid #d5a64f; } .alert-card { border-left: 3px solid #d96c54; }
.card-heading span { display: flex; min-width: 0; flex-direction: column; } .card-heading strong { font-size: 11px; color: #2e4339; } .card-heading em, article footer span, .evidence-row { font-size: 8px; font-style: normal; color: #85918b; }
p { margin: 6px 0; font-size: 9px; line-height: 1.5; color: #68776f; } article footer { min-height: 24px; margin-top: 6px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; } label { display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: #56665e; } label.wide { grid-column: 1 / -1; } label :deep(.ant-input-number), label :deep(.ant-select) { width: 100%; }
</style>
