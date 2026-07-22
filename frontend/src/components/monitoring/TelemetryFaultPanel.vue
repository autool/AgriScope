<script setup lang="ts">
import { message } from 'ant-design-vue'
import { computed, ref } from 'vue'

import type {
  DeviceFault,
  DeviceTelemetry,
  FaultCreatePayload,
  FaultResolvePayload,
  FaultSeverity,
  MonitoringDevice,
  TelemetryCreatePayload,
} from '@/types/monitoringNetwork'

const props = defineProps<{
  device: MonitoringDevice | null
  telemetry: DeviceTelemetry[]
  faults: DeviceFault[]
  canIngest: boolean
  canReportFault: boolean
  canResolveFault: boolean
  loading: boolean
}>()

const emit = defineEmits<{
  'ingest-telemetry': [deviceCode: string, payload: Omit<TelemetryCreatePayload, 'operator_code'>]
  'report-fault': [deviceCode: string, payload: Omit<FaultCreatePayload, 'operator_code'>]
  'resolve-fault': [faultCode: string, payload: Omit<FaultResolvePayload, 'operator_code'>]
}>()

const telemetryModalOpenRef = ref<boolean>(false)
const faultModalOpenRef = ref<boolean>(false)
const resolveModalOpenRef = ref<boolean>(false)
const selectedFaultRef = ref<DeviceFault | null>(null)
const idempotencyKeyRef = ref<string>('')
const observedAtRef = ref<string>('')
const metricCodeRef = ref<string>('')
const metricValueRef = ref<number | null>(null)
const metricUnitRef = ref<string>('')
const payloadJsonRef = ref<string>('{}')
const telemetryEvidenceUriRef = ref<string>('')
const telemetryEvidenceSizeRef = ref<number | null>(null)
const telemetryEvidenceShaRef = ref<string>('')
const faultCodeRef = ref<string>('')
const faultSeverityRef = ref<FaultSeverity>('major')
const faultReasonRef = ref<string>('')
const faultOccurredAtRef = ref<string>('')
const resolutionCommentRef = ref<string>('')
const resolutionUriRef = ref<string>('')
const resolutionSizeRef = ref<number | null>(null)
const resolutionShaRef = ref<string>('')

const deviceTelemetryComputed = computed(() => (
  props.device
    ? props.telemetry.filter((item) => item.device_code === props.device?.device_code)
    : []
))
const deviceFaultsComputed = computed(() => (
  props.device
    ? props.faults.filter((item) => item.device_code === props.device?.device_code)
    : []
))

const submitTelemetry = (): void => {
  if (!props.device || !idempotencyKeyRef.value || !observedAtRef.value || !metricCodeRef.value) {
    message.warning('请选择设备并填写幂等键、带时区观测时间和指标编码')
    return
  }
  let payload: Record<string, unknown>
  try {
    payload = JSON.parse(payloadJsonRef.value) as Record<string, unknown>
  } catch {
    message.warning('原始载荷必须是合法 JSON 对象')
    return
  }
  if (metricValueRef.value === null && !Object.keys(payload).length) {
    message.warning('请填写指标值或非空原始载荷')
    return
  }
  const hasEvidence = Boolean(
    telemetryEvidenceUriRef.value || telemetryEvidenceSizeRef.value || telemetryEvidenceShaRef.value,
  )
  if (hasEvidence && (
    !telemetryEvidenceUriRef.value || !telemetryEvidenceSizeRef.value
    || telemetryEvidenceShaRef.value.length !== 64
  )) {
    message.warning('遥测实体证据地址、大小和 64 位 SHA-256 必须同时填写')
    return
  }
  emit('ingest-telemetry', props.device.device_code, {
    idempotency_key: idempotencyKeyRef.value.trim(),
    observed_at: observedAtRef.value.trim(),
    metric_code: metricCodeRef.value.trim(),
    metric_value: metricValueRef.value,
    metric_unit: metricUnitRef.value.trim() || null,
    payload,
    ...(hasEvidence ? {
      evidence_uri: telemetryEvidenceUriRef.value.trim(),
      evidence_size_bytes: telemetryEvidenceSizeRef.value || undefined,
      evidence_sha256: telemetryEvidenceShaRef.value.trim(),
    } : {}),
  })
  telemetryModalOpenRef.value = false
}

const submitFault = (): void => {
  if (!props.device || !faultCodeRef.value || !faultReasonRef.value || !faultOccurredAtRef.value) {
    message.warning('请选择设备并完整填写故障编号、原因和带时区发生时间')
    return
  }
  emit('report-fault', props.device.device_code, {
    fault_code: faultCodeRef.value.trim(),
    severity: faultSeverityRef.value,
    reason: faultReasonRef.value.trim(),
    occurred_at: faultOccurredAtRef.value.trim(),
  })
  faultModalOpenRef.value = false
}

const openResolve = (fault: DeviceFault): void => {
  selectedFaultRef.value = fault
  resolveModalOpenRef.value = true
}

const submitResolution = (): void => {
  if (
    !selectedFaultRef.value || !resolutionCommentRef.value || !resolutionUriRef.value
    || !resolutionSizeRef.value || resolutionShaRef.value.length !== 64
  ) {
    message.warning('请完整填写处置说明、回执实体大小和 64 位 SHA-256')
    return
  }
  emit('resolve-fault', selectedFaultRef.value.fault_code, {
    resolution_comment: resolutionCommentRef.value.trim(),
    resolution_evidence_uri: resolutionUriRef.value.trim(),
    resolution_evidence_size_bytes: resolutionSizeRef.value,
    resolution_evidence_sha256: resolutionShaRef.value.trim(),
  })
  resolveModalOpenRef.value = false
}
</script>

<template>
  <section class="telemetry-panel">
    <header>
      <div><small>TELEMETRY & INCIDENTS</small><h3>遥测证据与设备故障</h3></div>
      <a-space>
        <a-button size="small" :disabled="!device || !canIngest" @click="telemetryModalOpenRef = true">写入遥测</a-button>
        <a-button
          size="small"
          danger
          :disabled="!device || !canReportFault"
          @click="faultModalOpenRef = true"
        >
          报告故障
        </a-button>
      </a-space>
    </header>
    <div v-if="device" class="device-summary">
      <span><strong>{{ device.device_name }}</strong><em>{{ device.device_code }} · {{ device.vendor }} / {{ device.model_number }}</em></span>
      <a-tag :color="device.status === 'online' ? 'green' : device.status === 'abnormal' ? 'red' : 'default'">{{ device.status }}</a-tag>
    </div>
    <a-empty v-else description="从左侧选择设备后查看遥测和故障闭环" />

    <div v-if="device" class="data-sections">
      <div class="section-title"><span>最近遥测</span><em>{{ deviceTelemetryComputed.length }} / 项目总览最近 200 条</em></div>
      <div v-if="deviceTelemetryComputed.length" class="telemetry-list">
        <article v-for="item in deviceTelemetryComputed" :key="item.idempotency_key">
          <span><strong>{{ item.metric_code }}</strong><em>{{ new Date(item.observed_at).toLocaleString() }}</em></span>
          <b>{{ item.metric_value ?? '载荷' }} {{ item.metric_unit || '' }}</b>
          <code>{{ item.idempotency_key }}</code>
        </article>
      </div>
      <a-empty v-else :image="null" description="尚无真实遥测" />

      <div class="section-title"><span>故障闭环</span><em>{{ deviceFaultsComputed.filter(item => item.status === 'open').length }} 条未关闭</em></div>
      <div v-if="deviceFaultsComputed.length" class="fault-list">
        <article v-for="fault in deviceFaultsComputed" :key="fault.fault_code">
          <div><a-tag :color="fault.severity === 'critical' ? 'red' : fault.severity === 'major' ? 'orange' : 'blue'">{{ fault.severity }}</a-tag><strong>{{ fault.fault_code }}</strong></div>
          <p>{{ fault.reason }}</p>
          <footer>
            <span>{{ fault.status }} · {{ new Date(fault.occurred_at).toLocaleString() }}</span><a-button
              v-if="fault.status === 'open'"
              size="small"
              type="link"
              :disabled="!canResolveFault"
              @click="openResolve(fault)"
            >
              提交处置证据
            </a-button>
          </footer>
        </article>
      </div>
      <a-empty v-else :image="null" description="没有设备故障记录" />
    </div>

    <a-modal
      v-model:open="telemetryModalOpenRef"
      title="幂等写入设备遥测"
      :confirm-loading="loading"
      width="720px"
      @ok="submitTelemetry"
    >
      <div class="form-grid">
        <label><span>幂等键</span><a-input v-model:value="idempotencyKeyRef" /></label>
        <label><span>观测时间</span><a-input v-model:value="observedAtRef" placeholder="ISO 8601，必须包含时区" /></label>
        <label><span>指标编码</span><a-input v-model:value="metricCodeRef" placeholder="如 soil.moisture" /></label>
        <label><span>指标单位</span><a-input v-model:value="metricUnitRef" /></label>
        <label><span>指标数值</span><a-input-number v-model:value="metricValueRef" /></label>
        <label class="wide"><span>原始 JSON 载荷</span><a-textarea v-model:value="payloadJsonRef" :rows="3" /></label>
        <label class="wide"><span>可选图像/文件证据 URI</span><a-input v-model:value="telemetryEvidenceUriRef" /></label>
        <label><span>证据大小（字节）</span><a-input-number v-model:value="telemetryEvidenceSizeRef" :min="1" /></label>
        <label><span>证据 SHA-256</span><a-input v-model:value="telemetryEvidenceShaRef" :maxlength="64" /></label>
      </div>
    </a-modal>

    <a-modal
      v-model:open="faultModalOpenRef"
      title="登记设备故障"
      :confirm-loading="loading"
      @ok="submitFault"
    >
      <div class="form-grid">
        <label><span>故障编号</span><a-input v-model:value="faultCodeRef" /></label>
        <label><span>严重度</span><a-select v-model:value="faultSeverityRef" :options="[{ value: 'minor', label: '轻微' }, { value: 'major', label: '严重' }, { value: 'critical', label: '紧急' }]" /></label>
        <label class="wide"><span>发生时间</span><a-input v-model:value="faultOccurredAtRef" placeholder="ISO 8601，必须包含时区" /></label>
        <label class="wide"><span>故障原因</span><a-textarea v-model:value="faultReasonRef" :rows="4" /></label>
      </div>
    </a-modal>

    <a-modal
      v-model:open="resolveModalOpenRef"
      title="提交故障处置实体证据"
      :confirm-loading="loading"
      @ok="submitResolution"
    >
      <div class="form-grid">
        <label class="wide"><span>处置说明</span><a-textarea v-model:value="resolutionCommentRef" :rows="3" /></label>
        <label class="wide"><span>处置回执 URI</span><a-input v-model:value="resolutionUriRef" /></label>
        <label><span>回执大小（字节）</span><a-input-number v-model:value="resolutionSizeRef" :min="1" /></label>
        <label><span>回执 SHA-256</span><a-input v-model:value="resolutionShaRef" :maxlength="64" /></label>
      </div>
    </a-modal>
  </section>
</template>

<style scoped>
.telemetry-panel { display: flex; flex-direction: column; min-height: 0; padding: 12px; overflow: hidden; background: #fff; border: 1px solid #dfe5e2; border-radius: 8px; }
header, .device-summary, .section-title, article footer { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
header { margin-bottom: 10px; }
small { font-size: 8px; color: #718078; letter-spacing: 1px; }
h3 { margin: 2px 0 0; font-size: 15px; color: #20352c; }
.device-summary { padding: 9px; background: #eff7f2; border: 1px solid #d8e9df; border-radius: 7px; }
.device-summary span { display: flex; flex-direction: column; }
strong { font-size: 12px; color: #294137; }
em { font-size: 9px; font-style: normal; color: #7c8a83; }
.data-sections { flex: 1; min-height: 0; padding-top: 10px; overflow: auto; }
.section-title { padding: 8px 2px 5px; font-size: 10px; color: #5d6e65; border-bottom: 1px solid #e6ebe8; }
.telemetry-list, .fault-list { display: flex; flex-direction: column; gap: 5px; padding: 6px 0; }
.telemetry-list article { display: grid; grid-template-columns: 1fr auto; gap: 3px 8px; padding: 7px; background: #f8faf9; border-radius: 6px; }
.telemetry-list article span { display: flex; flex-direction: column; }
.telemetry-list b { font-size: 12px; color: #347958; }
code { grid-column: 1 / -1; overflow: hidden; font-size: 8px; color: #8b9791; text-overflow: ellipsis; }
.fault-list article { padding: 8px; border: 1px solid #eadfdb; border-radius: 6px; }
.fault-list article > div { display: flex; align-items: center; gap: 5px; }
p { margin: 6px 0; font-size: 10px; color: #68776f; }
footer span { font-size: 9px; color: #8a9690; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
label { display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: #56665e; }
label.wide { grid-column: 1 / -1; }
label :deep(.ant-input-number), label :deep(.ant-select) { width: 100%; }
</style>
