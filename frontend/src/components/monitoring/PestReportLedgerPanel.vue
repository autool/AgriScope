<script setup lang="ts">
import { message } from 'ant-design-vue'
import type { UploadProps } from 'ant-design-vue'
import { computed, ref, shallowRef, watch } from 'vue'

import type {
  ConsultationAnswerMetadata,
  ConsultationCreatePayload,
  ExpertConsultation,
  PestAssessment,
  PestReport,
  PestReportCreatePayload,
  PestReportRevisePayload,
  PestReportScope,
} from '@/types/monitoringNetwork'

const props = defineProps<{
  reports: PestReport[]
  consultations: ExpertConsultation[]
  assessments: PestAssessment[]
  canManage: boolean
  canReviewCounty: boolean
  canReviewPrefecture: boolean
  canReviewProvince: boolean
  canAnswerConsultation: boolean
  canDownload: boolean
  loading: boolean
}>()

const emit = defineEmits<{
  create: [payload: Omit<PestReportCreatePayload, 'operator_code'>]
  revise: [reportCode: string, payload: Omit<PestReportRevisePayload, 'operator_code'>]
  'request-consultation': [reportCode: string, payload: Omit<ConsultationCreatePayload, 'operator_code'>]
  'answer-consultation': [consultationCode: string, file: File, metadata: ConsultationAnswerMetadata]
  submit: [reportCode: string, comment: string]
  review: [reportCode: string, action: 'approve' | 'return', comment: string]
  download: [reportCode: string, filename: string]
}>()

const selectedReportCodeRef = ref<string | null>(null)
const reportModalOpenRef = ref<boolean>(false)
const reportModeRef = ref<'create' | 'revise'>('create')
const actionModalOpenRef = ref<boolean>(false)
const actionRef = ref<'submit' | 'approve' | 'return'>('submit')
const actionCommentRef = ref<string>('')
const consultationModalOpenRef = ref<boolean>(false)
const consultationAnswerModalOpenRef = ref<boolean>(false)
const targetConsultationRef = ref<ExpertConsultation | null>(null)
const consultationFileRef = shallowRef<File | null>(null)

const reportCodeRef = ref<string>('')
const reportTitleRef = ref<string>('')
const scopeLevelRef = ref<PestReportScope>('province')
const regionCodeRef = ref<string>('')
const periodStartRef = ref<string>('')
const periodEndRef = ref<string>('')
const summaryRef = ref<string>('')
const conclusionRef = ref<string>('')
const assessmentCodesRef = ref<string[]>([])
const revisionCommentRef = ref<string>('')
const consultationCodeRef = ref<string>('')
const consultationQuestionRef = ref<string>('')
const expertOrganizationRef = ref<string>('')
const expertTitleRef = ref<string>('')
const expertResponseRef = ref<string>('')

const selectedReportComputed = computed<PestReport | null>(() => (
  props.reports.find((item) => item.report_code === selectedReportCodeRef.value)
  || props.reports[0]
  || null
))
const selectedConsultationsComputed = computed(() => (
  selectedReportComputed.value
    ? props.consultations.filter(
      (item) => item.report_code === selectedReportComputed.value?.report_code,
    )
    : []
))
const approvedAssessmentOptionsComputed = computed(() => (
  props.assessments
    .filter((item) => item.status === 'approved' && item.device_code)
    .map((item) => ({
      value: item.assessment_code,
      label: `${item.assessment_code} · ${item.target_name} · ${item.prediction_label}`,
    }))
))

const statusLabels: Record<PestReport['status'], string> = {
  draft: '草稿',
  county_review: '县级审核',
  prefecture_review: '地级审核',
  province_review: '省级审核',
  returned: '已退回',
  approved: '已批准',
}
const scopeLabels: Record<PestReportScope, string> = {
  province: '省级',
  prefecture: '地级',
  county: '县级',
}

const canReviewSelectedComputed = computed<boolean>(() => {
  const status = selectedReportComputed.value?.status
  if (status === 'county_review') return props.canReviewCounty
  if (status === 'prefecture_review') return props.canReviewPrefecture
  if (status === 'province_review') return props.canReviewProvince
  return false
})

watch(() => props.reports, (reports) => {
  if (!reports.length) {
    selectedReportCodeRef.value = null
    return
  }
  if (!reports.some((item) => item.report_code === selectedReportCodeRef.value)) {
    selectedReportCodeRef.value = reports[0].report_code
  }
}, { deep: true, immediate: true })

const resetReportForm = (): void => {
  reportCodeRef.value = ''
  reportTitleRef.value = ''
  scopeLevelRef.value = 'province'
  regionCodeRef.value = ''
  periodStartRef.value = ''
  periodEndRef.value = ''
  summaryRef.value = ''
  conclusionRef.value = ''
  assessmentCodesRef.value = []
  revisionCommentRef.value = ''
}

const openCreate = (): void => {
  resetReportForm()
  reportModeRef.value = 'create'
  reportModalOpenRef.value = true
}

const openRevise = (): void => {
  const report = selectedReportComputed.value
  if (!report) return
  reportModeRef.value = 'revise'
  reportCodeRef.value = report.report_code
  reportTitleRef.value = report.report_title
  scopeLevelRef.value = report.scope_level
  regionCodeRef.value = report.region_code
  periodStartRef.value = report.period_start
  periodEndRef.value = report.period_end
  summaryRef.value = report.summary
  conclusionRef.value = report.conclusion
  assessmentCodesRef.value = report.items.map((item) => item.assessment_code)
  revisionCommentRef.value = ''
  reportModalOpenRef.value = true
}

const submitReportForm = (): void => {
  if (
    !reportTitleRef.value.trim() || !regionCodeRef.value.trim()
    || !periodStartRef.value || !periodEndRef.value
    || summaryRef.value.trim().length < 10 || conclusionRef.value.trim().length < 10
    || !assessmentCodesRef.value.length
  ) {
    message.warning('请完整填写报告范围、周期、内容并显式选择已批准识别结果')
    return
  }
  const common = {
    report_title: reportTitleRef.value.trim(),
    scope_level: scopeLevelRef.value,
    region_code: regionCodeRef.value.trim(),
    period_start: periodStartRef.value,
    period_end: periodEndRef.value,
    summary: summaryRef.value.trim(),
    conclusion: conclusionRef.value.trim(),
    assessment_codes: assessmentCodesRef.value,
  }
  if (reportModeRef.value === 'create') {
    if (!reportCodeRef.value.trim()) {
      message.warning('请填写报告编号')
      return
    }
    emit('create', { report_code: reportCodeRef.value.trim(), ...common })
  } else {
    if (revisionCommentRef.value.trim().length < 8) {
      message.warning('请填写不少于 8 个字符的修订依据')
      return
    }
    emit('revise', reportCodeRef.value, {
      ...common,
      revision_comment: revisionCommentRef.value.trim(),
    })
  }
  reportModalOpenRef.value = false
}

const openAction = (action: 'submit' | 'approve' | 'return'): void => {
  actionRef.value = action
  actionCommentRef.value = ''
  actionModalOpenRef.value = true
}

const submitAction = (): void => {
  const report = selectedReportComputed.value
  if (!report || actionCommentRef.value.trim().length < 4) {
    message.warning('请填写审核或提交依据')
    return
  }
  if (actionRef.value === 'submit') {
    emit('submit', report.report_code, actionCommentRef.value.trim())
  } else {
    emit('review', report.report_code, actionRef.value, actionCommentRef.value.trim())
  }
  actionModalOpenRef.value = false
}

const submitConsultation = (): void => {
  const report = selectedReportComputed.value
  if (!report || !consultationCodeRef.value.trim() || consultationQuestionRef.value.trim().length < 8) {
    message.warning('请填写会商编号和明确问题')
    return
  }
  emit('request-consultation', report.report_code, {
    consultation_code: consultationCodeRef.value.trim(),
    question: consultationQuestionRef.value.trim(),
  })
  consultationModalOpenRef.value = false
}

const openAnswer = (consultation: ExpertConsultation): void => {
  targetConsultationRef.value = consultation
  consultationFileRef.value = null
  expertOrganizationRef.value = ''
  expertTitleRef.value = ''
  expertResponseRef.value = ''
  consultationAnswerModalOpenRef.value = true
}

const beforeConsultationUpload: UploadProps['beforeUpload'] = (file) => {
  consultationFileRef.value = file
  return false
}

const submitConsultationAnswer = (): void => {
  if (
    !targetConsultationRef.value || !consultationFileRef.value
    || !expertOrganizationRef.value.trim() || !expertTitleRef.value.trim()
    || expertResponseRef.value.trim().length < 8
  ) {
    message.warning('请填写专家单位、专业身份、答复并选择实体证据')
    return
  }
  emit(
    'answer-consultation',
    targetConsultationRef.value.consultation_code,
    consultationFileRef.value,
    {
      expertOrganization: expertOrganizationRef.value.trim(),
      expertTitle: expertTitleRef.value.trim(),
      response: expertResponseRef.value.trim(),
    },
  )
  consultationAnswerModalOpenRef.value = false
}
</script>

<template>
  <section class="report-panel">
    <header>
      <div><small>REPORT & LEDGER</small><h3>病虫害报告、分级审核与专家会商</h3></div>
      <a-space size="small">
        <a-button size="small" :disabled="!canManage" @click="openCreate">创建报告</a-button>
        <a-button
          size="small"
          :disabled="!canManage || !selectedReportComputed || !['draft', 'returned'].includes(selectedReportComputed.status)"
          @click="openRevise"
        >
          修订
        </a-button>
        <a-button
          size="small"
          :disabled="!canManage || !selectedReportComputed || !['draft', 'returned'].includes(selectedReportComputed.status)"
          @click="consultationModalOpenRef = true"
        >
          发起会商
        </a-button>
      </a-space>
    </header>
    <div class="report-workspace">
      <aside class="report-list">
        <button
          v-for="report in reports"
          :key="report.report_code"
          type="button"
          :class="{ selected: selectedReportComputed?.report_code === report.report_code }"
          @click="selectedReportCodeRef = report.report_code"
        >
          <span><strong>{{ report.report_title }}</strong><em>{{ report.report_code }} · v{{ report.revision_number }}</em></span>
          <a-tag :color="report.status === 'approved' ? 'green' : report.status === 'returned' ? 'red' : 'blue'">{{ statusLabels[report.status] }}</a-tag>
          <p>{{ report.region_name }} · {{ report.assessment_count }} 条识别 · {{ report.open_consultation_count }} 个会商待答</p>
        </button>
        <a-empty v-if="!reports.length" :image="false" description="尚未从真实识别结果创建监测报告" />
      </aside>
      <main v-if="selectedReportComputed" class="report-detail">
        <div class="detail-heading">
          <span><strong>{{ selectedReportComputed.report_title }}</strong><em>{{ scopeLabels[selectedReportComputed.scope_level] }} · {{ selectedReportComputed.region_name }} · {{ selectedReportComputed.period_start }} 至 {{ selectedReportComputed.period_end }}</em></span>
          <a-space size="small">
            <a-button
              v-if="['draft', 'returned'].includes(selectedReportComputed.status)"
              size="small"
              type="primary"
              :disabled="!canManage || selectedReportComputed.open_consultation_count > 0"
              @click="openAction('submit')"
            >
              提交县级审核
            </a-button>
            <template v-if="canReviewSelectedComputed">
              <a-button size="small" danger @click="openAction('return')">退回</a-button>
              <a-button size="small" type="primary" @click="openAction('approve')">本级通过</a-button>
            </template>
            <a-button
              v-if="selectedReportComputed.status === 'approved' && selectedReportComputed.original_filename"
              size="small"
              :disabled="!canDownload"
              @click="emit('download', selectedReportComputed.report_code, selectedReportComputed.original_filename)"
            >
              下载 XLSX 台账
            </a-button>
          </a-space>
        </div>
        <div class="report-summary">
          <p>{{ selectedReportComputed.summary }}</p>
          <p><b>结论：</b>{{ selectedReportComputed.conclusion }}</p>
          <div>
            <span>识别台账 <strong>{{ selectedReportComputed.assessment_count }}</strong></span>
            <span>关联告警 <strong>{{ selectedReportComputed.alert_count }}</strong></span>
            <span>会商 <strong>{{ selectedReportComputed.consultation_count }}</strong></span>
            <span v-if="selectedReportComputed.checksum_sha256">SHA {{ selectedReportComputed.checksum_sha256.slice(0, 12) }}…</span>
          </div>
        </div>
        <div class="consultation-list">
          <article v-for="item in selectedConsultationsComputed" :key="item.consultation_code">
            <span><strong>{{ item.consultation_code }}</strong><em>{{ item.question }}</em></span>
            <a-tag :color="item.status === 'answered' ? 'green' : 'orange'">{{ item.status === 'answered' ? '已答复' : '待答复' }}</a-tag>
            <p v-if="item.response">{{ item.expert_organization }} · {{ item.expert_title }}：{{ item.response }}</p>
            <a-button
              v-if="item.status === 'open'"
              size="small"
              type="link"
              :disabled="!canAnswerConsultation"
              @click="openAnswer(item)"
            >
              上传专家答复
            </a-button>
          </article>
          <a-empty v-if="!selectedConsultationsComputed.length" :image="false" description="当前报告未发起专家会商" />
        </div>
      </main>
      <a-empty v-else description="选择报告查看审核与会商状态" />
    </div>

    <a-modal
      v-model:open="reportModalOpenRef"
      :title="reportModeRef === 'create' ? '创建病虫害监测报告' : '修订退回报告'"
      width="820px"
      :confirm-loading="loading"
      @ok="submitReportForm"
    >
      <div class="form-grid">
        <label><span>报告编号</span><a-input v-model:value="reportCodeRef" :disabled="reportModeRef === 'revise'" /></label>
        <label><span>报告标题</span><a-input v-model:value="reportTitleRef" /></label>
        <label><span>行政层级</span><a-select v-model:value="scopeLevelRef" :options="[{ value: 'province', label: '省级' }, { value: 'prefecture', label: '地级' }, { value: 'county', label: '县级' }]" /></label>
        <label><span>真实行政区编码</span><a-input v-model:value="regionCodeRef" /></label>
        <label><span>周期开始</span><a-input v-model:value="periodStartRef" type="date" /></label>
        <label><span>周期结束</span><a-input v-model:value="periodEndRef" type="date" /></label>
        <label class="wide"><span>显式选择已批准识别结果</span><a-select v-model:value="assessmentCodesRef" mode="multiple" :options="approvedAssessmentOptionsComputed" /></label>
        <label class="wide"><span>监测摘要</span><a-textarea v-model:value="summaryRef" :rows="3" /></label>
        <label class="wide"><span>结论与防控建议</span><a-textarea v-model:value="conclusionRef" :rows="3" /></label>
        <label v-if="reportModeRef === 'revise'" class="wide"><span>修订依据</span><a-textarea v-model:value="revisionCommentRef" :rows="2" /></label>
      </div>
    </a-modal>

    <a-modal
      v-model:open="actionModalOpenRef"
      :title="actionRef === 'submit' ? '提交县级审核' : actionRef === 'approve' ? '本级审核通过' : '退回报告整改'"
      :confirm-loading="loading"
      @ok="submitAction"
    >
      <a-textarea v-model:value="actionCommentRef" :rows="5" placeholder="填写范围、台账、会商或整改审核依据" />
    </a-modal>

    <a-modal
      v-model:open="consultationModalOpenRef"
      title="发起专家会商"
      :confirm-loading="loading"
      @ok="submitConsultation"
    >
      <div class="form-grid one-column">
        <label><span>会商编号</span><a-input v-model:value="consultationCodeRef" /></label>
        <label><span>待研判问题</span><a-textarea v-model:value="consultationQuestionRef" :rows="5" /></label>
      </div>
    </a-modal>

    <a-modal
      v-model:open="consultationAnswerModalOpenRef"
      title="登记专家会商答复"
      :confirm-loading="loading"
      @ok="submitConsultationAnswer"
    >
      <div class="form-grid">
        <label><span>专家单位</span><a-input v-model:value="expertOrganizationRef" /></label>
        <label><span>职称/专业身份</span><a-input v-model:value="expertTitleRef" /></label>
        <label class="wide"><span>会商答复</span><a-textarea v-model:value="expertResponseRef" :rows="5" /></label>
        <label class="wide"><span>签字意见或会商纪要实体</span><a-upload :before-upload="beforeConsultationUpload" :max-count="1"><a-button>选择 PDF、Office、图片或 ZIP</a-button></a-upload></label>
      </div>
    </a-modal>
  </section>
</template>

<style scoped>
.report-panel { display: flex; min-height: 0; flex-direction: column; padding: 12px; overflow: hidden; background: #fff; border: 1px solid #dfe5e2; border-radius: 8px; }
header, .detail-heading, .report-summary > div { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
header { margin-bottom: 8px; } small { font-size: 8px; color: #718078; letter-spacing: 1px; } h3 { margin: 2px 0 0; font-size: 15px; color: #20352c; }
.report-workspace { display: grid; grid-template-columns: minmax(280px, .75fr) minmax(0, 2fr); gap: 8px; min-height: 0; flex: 1; }
.report-list, .consultation-list { display: flex; min-height: 0; flex-direction: column; gap: 5px; overflow: auto; }
.report-list button, .consultation-list article { position: relative; padding: 8px; text-align: left; background: #f8faf9; border: 1px solid #e2e7e4; border-radius: 6px; }
.report-list button { cursor: pointer; } .report-list button.selected { background: #edf7f1; border-color: #76b38f; }
.report-list span, .detail-heading > span, .consultation-list article > span { display: flex; min-width: 0; flex-direction: column; padding-right: 70px; }
.report-list :deep(.ant-tag), .consultation-list :deep(.ant-tag) { position: absolute; top: 7px; right: 5px; }
strong { font-size: 11px; color: #294137; } em { overflow: hidden; font-size: 8px; font-style: normal; color: #7c8a83; text-overflow: ellipsis; white-space: nowrap; } p { margin: 5px 0; font-size: 9px; color: #68776f; }
.report-detail { display: grid; grid-template-rows: auto auto minmax(0, 1fr); gap: 7px; min-width: 0; min-height: 0; }
.detail-heading { padding-bottom: 7px; border-bottom: 1px solid #e5eae7; } .detail-heading > span { padding-right: 0; }
.report-summary { padding: 7px 9px; background: #f5f9f7; border: 1px solid #dde8e1; border-radius: 6px; } .report-summary > div { justify-content: flex-start; margin-top: 6px; font-size: 8px; color: #718078; } .report-summary > div span { padding-right: 12px; border-right: 1px solid #dce4df; } .report-summary > div span:last-child { border-right: 0; }
.consultation-list article p { padding-right: 80px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; } .form-grid.one-column { grid-template-columns: 1fr; } label { display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: #56665e; } label.wide { grid-column: 1 / -1; } label :deep(.ant-select) { width: 100%; }
</style>
