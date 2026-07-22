<script setup lang="ts">
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, ref, watch } from 'vue'

import MonitoringResourcePanel from '@/components/monitoring/MonitoringResourcePanel.vue'
import PestIntelligencePanel from '@/components/monitoring/PestIntelligencePanel.vue'
import PestReportLedgerPanel from '@/components/monitoring/PestReportLedgerPanel.vue'
import TelemetryFaultPanel from '@/components/monitoring/TelemetryFaultPanel.vue'
import { useMonitoringNetworkStore } from '@/store/monitoringNetworkStore'
import { useUserStore } from '@/store/userStore'
import type {
  AlertCreatePayload,
  AssessmentCreatePayload,
  ConsultationAnswerMetadata,
  ConsultationCreatePayload,
  DeviceCreatePayload,
  FaultCreatePayload,
  FaultResolvePayload,
  PestModelCreatePayload,
  PestReportCreatePayload,
  PestReportRevisePayload,
  StationCreatePayload,
  TelemetryCreatePayload,
} from '@/types/monitoringNetwork'

const monitoringStore = useMonitoringNetworkStore()
const userStore = useUserStore()
const {
  canDeliverAlertComputed,
  canAnswerConsultationComputed,
  canDownloadReportComputed,
  canIngestComputed,
  canManageDevicesComputed,
  canManageModelsComputed,
  canManageReportsComputed,
  canReportFaultComputed,
  canReviewComputed,
  canReviewCountyReportComputed,
  canReviewPrefectureReportComputed,
  canReviewProvinceReportComputed,
  loadingRef,
  mutatingRef,
  overviewRef,
} = storeToRefs(monitoringStore)
const selectedDeviceCodeRef = ref<string | null>(null)
const selectedDeviceComputed = computed(() => (
  overviewRef.value?.devices.find(
    (item) => item.device_code === selectedDeviceCodeRef.value,
  ) || overviewRef.value?.devices[0] || null
))

const loadOverview = async (): Promise<void> => {
  try {
    await monitoringStore.load()
  } catch {
    // 请求层已显示安全错误提示，保留真实空态。
  }
}

watch(
  () => userStore.currentUserComputed?.user_code,
  (userCode) => {
    if (userCode) void loadOverview()
  },
  { immediate: true },
)

watch(() => overviewRef.value?.devices, (devices) => {
  if (!devices?.length) {
    selectedDeviceCodeRef.value = null
    return
  }
  if (!devices.some((item) => item.device_code === selectedDeviceCodeRef.value)) {
    selectedDeviceCodeRef.value = devices[0].device_code
  }
}, { deep: true })

const runAction = async (
  action: () => Promise<void>,
  success: string,
): Promise<void> => {
  try {
    await action()
    message.success(success)
  } catch {
    // 请求层已统一显示后端安全错误信息。
  }
}

const handleStation = (
  payload: Omit<StationCreatePayload, 'operator_code'>,
): void => {
  void runAction(() => monitoringStore.registerStation(payload), '监测站已登记并完成行政区坐标校验')
}

const handleDevice = (
  stationCode: string,
  payload: Omit<DeviceCreatePayload, 'operator_code'>,
): void => {
  void runAction(() => monitoringStore.registerDevice(stationCode, payload), '监测设备及照片证据已登记')
}

const handleTelemetry = (
  deviceCode: string,
  payload: Omit<TelemetryCreatePayload, 'operator_code'>,
): void => {
  void runAction(() => monitoringStore.ingestTelemetry(deviceCode, payload), '遥测已通过幂等接口写入')
}

const handleFault = (
  deviceCode: string,
  payload: Omit<FaultCreatePayload, 'operator_code'>,
): void => {
  void runAction(() => monitoringStore.reportFault(deviceCode, payload), '设备故障已进入处置队列')
}

const handleResolveFault = (
  faultCode: string,
  payload: Omit<FaultResolvePayload, 'operator_code'>,
): void => {
  void runAction(() => monitoringStore.resolveFault(faultCode, payload), '故障已凭实体证据完成闭环')
}

const handleModel = (
  payload: Omit<PestModelCreatePayload, 'operator_code'>,
): void => {
  void runAction(() => monitoringStore.registerModel(payload), '模型实体版本和评估指标已登记')
}

const handleAssessment = (
  payload: Omit<AssessmentCreatePayload, 'operator_code'>,
): void => {
  void runAction(() => monitoringStore.submitAssessment(payload), '识别结果已进入人工复核队列')
}

const handleReview = (
  assessmentCode: string,
  decision: 'approve' | 'reject',
  comment: string,
): void => {
  void runAction(
    () => monitoringStore.reviewAssessment(assessmentCode, decision, comment),
    decision === 'approve' ? '识别结果已人工批准' : '识别结果已驳回',
  )
}

const handleAlert = (
  assessmentCode: string,
  payload: Omit<AlertCreatePayload, 'operator_code'>,
): void => {
  void runAction(() => monitoringStore.createAlert(assessmentCode, payload), '告警已创建，等待真实送达回执')
}

const handleDeliverAlert = (
  alertCode: string,
  receiptUri: string,
  receiptSize: number,
  receiptSha: string,
): void => {
  void runAction(
    () => monitoringStore.deliverAlert(alertCode, receiptUri, receiptSize, receiptSha),
    '告警送达回执已校验登记',
  )
}

const handleCreateReport = (
  payload: Omit<PestReportCreatePayload, 'operator_code'>,
): void => {
  void runAction(() => monitoringStore.createReport(payload), '病虫害报告草稿和显式识别台账已创建')
}

const handleReviseReport = (
  reportCode: string,
  payload: Omit<PestReportRevisePayload, 'operator_code'>,
): void => {
  void runAction(() => monitoringStore.reviseReport(reportCode, payload), '退回报告已修订并重建识别快照')
}

const handleRequestConsultation = (
  reportCode: string,
  payload: Omit<ConsultationCreatePayload, 'operator_code'>,
): void => {
  void runAction(() => monitoringStore.requestConsultation(reportCode, payload), '专家会商问题已登记')
}

const handleAnswerConsultation = (
  consultationCode: string,
  file: File,
  metadata: ConsultationAnswerMetadata,
): void => {
  void runAction(
    () => monitoringStore.answerConsultation(consultationCode, file, metadata),
    '专家会商答复实体及服务端校验值已登记',
  )
}

const handleSubmitReport = (reportCode: string, comment: string): void => {
  void runAction(() => monitoringStore.submitReport(reportCode, comment), '报告已提交县级审核')
}

const handleReviewReport = (
  reportCode: string,
  action: 'approve' | 'return',
  comment: string,
): void => {
  void runAction(
    () => monitoringStore.reviewReport(reportCode, action, comment),
    action === 'return' ? '报告已退回整改' : '报告已通过当前审核层级',
  )
}

const handleDownloadReport = (reportCode: string, filename: string): void => {
  void runAction(
    () => monitoringStore.downloadReport(reportCode, filename),
    '报告实体校验通过，已开始下载',
  )
}
</script>

<template>
  <div class="monitoring-view">
    <section class="summary-strip">
      <span><small>STATIONS</small><strong>{{ overviewRef?.station_count || 0 }}</strong><em>真实监测站</em></span>
      <span><small>DEVICES</small><strong>{{ overviewRef?.device_count || 0 }}</strong><em>{{ overviewRef?.online_device_count || 0 }} 台在线</em></span>
      <span><small>TELEMETRY</small><strong>{{ overviewRef?.telemetry_count || 0 }}</strong><em>幂等遥测总数</em></span>
      <span><small>FAULTS</small><strong>{{ overviewRef?.open_fault_count || 0 }}</strong><em>未关闭故障</em></span>
      <span><small>AI REVIEW</small><strong>{{ overviewRef?.pending_assessment_count || 0 }}</strong><em>待人工复核</em></span>
      <span><small>ALERTS</small><strong>{{ overviewRef?.pending_alert_count || 0 }}</strong><em>待登记送达</em></span>
      <span><small>REPORTS</small><strong>{{ overviewRef?.pending_report_count || 0 }}</strong><em>{{ overviewRef?.report_count || 0 }} 份报告</em></span>
      <span><small>CONSULT</small><strong>{{ overviewRef?.open_consultation_count || 0 }}</strong><em>会商待答</em></span>
    </section>
    <a-spin :spinning="loadingRef" class="workspace-spin">
      <section class="workspace-grid">
        <MonitoringResourcePanel
          :stations="overviewRef?.stations || []"
          :devices="overviewRef?.devices || []"
          :selected-device-code="selectedDeviceComputed?.device_code || null"
          :can-manage="canManageDevicesComputed"
          :loading="mutatingRef"
          @select-device="selectedDeviceCodeRef = $event"
          @register-station="handleStation"
          @register-device="handleDevice"
        />
        <TelemetryFaultPanel
          :device="selectedDeviceComputed"
          :telemetry="overviewRef?.telemetry || []"
          :faults="overviewRef?.faults || []"
          :can-ingest="canIngestComputed"
          :can-report-fault="canReportFaultComputed"
          :can-resolve-fault="canManageDevicesComputed"
          :loading="mutatingRef"
          @ingest-telemetry="handleTelemetry"
          @report-fault="handleFault"
          @resolve-fault="handleResolveFault"
        />
        <PestIntelligencePanel
          :models="overviewRef?.models || []"
          :assessments="overviewRef?.assessments || []"
          :alerts="overviewRef?.alerts || []"
          :devices="overviewRef?.devices || []"
          :can-manage-models="canManageModelsComputed"
          :can-ingest="canIngestComputed"
          :can-review="canReviewComputed"
          :can-deliver-alert="canDeliverAlertComputed"
          :loading="mutatingRef"
          @register-model="handleModel"
          @submit-assessment="handleAssessment"
          @review-assessment="handleReview"
          @create-alert="handleAlert"
          @deliver-alert="handleDeliverAlert"
        />
        <PestReportLedgerPanel
          class="report-ledger"
          :reports="overviewRef?.reports || []"
          :consultations="overviewRef?.consultations || []"
          :assessments="overviewRef?.assessments || []"
          :can-manage="canManageReportsComputed"
          :can-review-county="canReviewCountyReportComputed"
          :can-review-prefecture="canReviewPrefectureReportComputed"
          :can-review-province="canReviewProvinceReportComputed"
          :can-answer-consultation="canAnswerConsultationComputed"
          :can-download="canDownloadReportComputed"
          :loading="mutatingRef"
          @create="handleCreateReport"
          @revise="handleReviseReport"
          @request-consultation="handleRequestConsultation"
          @answer-consultation="handleAnswerConsultation"
          @submit="handleSubmitReport"
          @review="handleReviewReport"
          @download="handleDownloadReport"
        />
      </section>
    </a-spin>
  </div>
</template>

<style scoped>
.monitoring-view { display: grid; grid-template-rows: auto minmax(0, 1fr); gap: 10px; height: 100%; padding: 10px; background: #eef2f0; }
.summary-strip { display: grid; grid-template-columns: repeat(8, minmax(90px, 1fr)); gap: 7px; }
.summary-strip span { display: flex; flex-direction: column; padding: 9px 11px; background: #fff; border: 1px solid #dfe5e2; border-radius: 7px; }
.summary-strip small { font-size: 7px; color: #8b9791; letter-spacing: .8px; }
.summary-strip strong { font-size: 19px; color: #347958; }
.summary-strip em { font-size: 8px; font-style: normal; color: #77867e; }
.workspace-spin { min-height: 0; }
.workspace-spin :deep(.ant-spin-container) { height: 100%; min-height: 0; }
.workspace-grid { display: grid; grid-template-rows: minmax(480px, 1fr) minmax(330px, .72fr); grid-template-columns: minmax(330px, .9fr) minmax(400px, 1.05fr) minmax(440px, 1.15fr); gap: 9px; height: 100%; min-height: 0; overflow: auto; }
.report-ledger { grid-column: 1 / -1; }
@media (max-width: 1320px) { .summary-strip { grid-template-columns: repeat(4, 1fr); } .workspace-grid { grid-template-rows: auto; grid-template-columns: 1fr 1fr; } .workspace-grid > :nth-child(3), .report-ledger { grid-column: 1 / -1; min-height: 560px; } }
</style>
