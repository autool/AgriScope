import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  answerExpertConsultation,
  createExpertConsultation,
  createDeviceFault,
  createDeviceTelemetry,
  createMonitoringDevice,
  createMonitoringStation,
  createPestAlert,
  createPestAssessment,
  createPestModel,
  createPestReport,
  downloadPestReport,
  deliverPestAlert,
  getMonitoringOverview,
  resolveDeviceFault,
  revisePestReport,
  reviewPestReport as reviewPestReportApi,
  reviewPestAssessment,
  submitPestReport,
} from '@/api/monitoringNetwork'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  AlertCreatePayload,
  AssessmentCreatePayload,
  ConsultationAnswerMetadata,
  ConsultationCreatePayload,
  DeviceCreatePayload,
  FaultCreatePayload,
  FaultResolvePayload,
  MonitoringOverview,
  PestModelCreatePayload,
  PestReportCreatePayload,
  PestReportRevisePayload,
  StationCreatePayload,
  TelemetryCreatePayload,
} from '@/types/monitoringNetwork'

export const useMonitoringNetworkStore = defineStore('monitoringNetwork', () => {
  const workbenchStore = useWorkbenchStore()
  const userStore = useUserStore()
  const overviewRef = ref<MonitoringOverview | null>(null)
  const loadingRef = ref<boolean>(false)
  const mutatingRef = ref<boolean>(false)

  const canManageDevicesComputed = computed<boolean>(() => (
    userStore.hasCapability('manage_devices')
  ))
  const canIngestComputed = computed<boolean>(() => (
    userStore.hasCapability('ingest_monitoring_data')
  ))
  const canReportFaultComputed = computed<boolean>(() => (
    userStore.hasCapability('report_device_fault')
  ))
  const canManageModelsComputed = computed<boolean>(() => (
    userStore.hasCapability('manage_monitoring_models')
  ))
  const canReviewComputed = computed<boolean>(() => (
    userStore.hasCapability('review_model_output')
  ))
  const canDeliverAlertComputed = computed<boolean>(() => (
    userStore.hasCapability('deliver_pest_alert')
  ))
  const canManageReportsComputed = computed<boolean>(() => (
    userStore.hasCapability('manage_pest_reports')
  ))
  const canReviewCountyReportComputed = computed<boolean>(() => (
    userStore.hasCapability('review_county_pest_report')
  ))
  const canReviewPrefectureReportComputed = computed<boolean>(() => (
    userStore.hasCapability('review_prefecture_pest_report')
  ))
  const canReviewProvinceReportComputed = computed<boolean>(() => (
    userStore.hasCapability('review_province_pest_report')
  ))
  const canAnswerConsultationComputed = computed<boolean>(() => (
    userStore.hasCapability('answer_pest_consultation')
  ))
  const canDownloadReportComputed = computed<boolean>(() => (
    userStore.hasCapability('download_pest_report')
  ))

  const requireUserCode = (): string => {
    const userCode = userStore.currentUserComputed?.user_code
    if (!userCode) throw new Error('当前项目用户尚未加载')
    return userCode
  }

  const load = async (): Promise<void> => {
    const userCode = requireUserCode()
    loadingRef.value = true
    try {
      overviewRef.value = await getMonitoringOverview(
        workbenchStore.projectCodeComputed,
        userCode,
      )
    } finally {
      loadingRef.value = false
    }
  }

  const mutate = async (action: () => Promise<unknown>): Promise<void> => {
    mutatingRef.value = true
    try {
      await action()
      await load()
    } finally {
      mutatingRef.value = false
    }
  }

  const registerStation = async (
    payload: Omit<StationCreatePayload, 'operator_code'>,
  ): Promise<void> => mutate(() => createMonitoringStation(
    workbenchStore.projectCodeComputed,
    { ...payload, operator_code: requireUserCode() },
  ))

  const registerDevice = async (
    stationCode: string,
    payload: Omit<DeviceCreatePayload, 'operator_code'>,
  ): Promise<void> => mutate(() => createMonitoringDevice(
    workbenchStore.projectCodeComputed,
    stationCode,
    { ...payload, operator_code: requireUserCode() },
  ))

  const ingestTelemetry = async (
    deviceCode: string,
    payload: Omit<TelemetryCreatePayload, 'operator_code'>,
  ): Promise<void> => mutate(() => createDeviceTelemetry(
    workbenchStore.projectCodeComputed,
    deviceCode,
    { ...payload, operator_code: requireUserCode() },
  ))

  const reportFault = async (
    deviceCode: string,
    payload: Omit<FaultCreatePayload, 'operator_code'>,
  ): Promise<void> => mutate(() => createDeviceFault(
    workbenchStore.projectCodeComputed,
    deviceCode,
    { ...payload, operator_code: requireUserCode() },
  ))

  const resolveFault = async (
    faultCode: string,
    payload: Omit<FaultResolvePayload, 'operator_code'>,
  ): Promise<void> => mutate(() => resolveDeviceFault(
    workbenchStore.projectCodeComputed,
    faultCode,
    { ...payload, operator_code: requireUserCode() },
  ))

  const registerModel = async (
    payload: Omit<PestModelCreatePayload, 'operator_code'>,
  ): Promise<void> => mutate(() => createPestModel(
    workbenchStore.projectCodeComputed,
    { ...payload, operator_code: requireUserCode() },
  ))

  const submitAssessment = async (
    payload: Omit<AssessmentCreatePayload, 'operator_code'>,
  ): Promise<void> => mutate(() => createPestAssessment(
    workbenchStore.projectCodeComputed,
    { ...payload, operator_code: requireUserCode() },
  ))

  const reviewAssessment = async (
    assessmentCode: string,
    decision: 'approve' | 'reject',
    comment: string,
  ): Promise<void> => mutate(() => reviewPestAssessment(
    workbenchStore.projectCodeComputed,
    assessmentCode,
    decision,
    comment,
    requireUserCode(),
  ))

  const createAlert = async (
    assessmentCode: string,
    payload: Omit<AlertCreatePayload, 'operator_code'>,
  ): Promise<void> => mutate(() => createPestAlert(
    workbenchStore.projectCodeComputed,
    assessmentCode,
    { ...payload, operator_code: requireUserCode() },
  ))

  const deliverAlert = async (
    alertCode: string,
    receiptUri: string,
    receiptSizeBytes: number,
    receiptSha256: string,
  ): Promise<void> => mutate(() => deliverPestAlert(
    workbenchStore.projectCodeComputed,
    alertCode,
    receiptUri,
    receiptSizeBytes,
    receiptSha256,
    requireUserCode(),
  ))

  const createReport = async (
    payload: Omit<PestReportCreatePayload, 'operator_code'>,
  ): Promise<void> => mutate(() => createPestReport(
    workbenchStore.projectCodeComputed,
    { ...payload, operator_code: requireUserCode() },
  ))

  const reviseReport = async (
    reportCode: string,
    payload: Omit<PestReportRevisePayload, 'operator_code'>,
  ): Promise<void> => mutate(() => revisePestReport(
    workbenchStore.projectCodeComputed,
    reportCode,
    { ...payload, operator_code: requireUserCode() },
  ))

  const requestConsultation = async (
    reportCode: string,
    payload: Omit<ConsultationCreatePayload, 'operator_code'>,
  ): Promise<void> => mutate(() => createExpertConsultation(
    workbenchStore.projectCodeComputed,
    reportCode,
    { ...payload, operator_code: requireUserCode() },
  ))

  const answerConsultation = async (
    consultationCode: string,
    file: File,
    metadata: ConsultationAnswerMetadata,
  ): Promise<void> => mutate(() => answerExpertConsultation(
    workbenchStore.projectCodeComputed,
    consultationCode,
    file,
    metadata,
    requireUserCode(),
  ))

  const submitReport = async (
    reportCode: string,
    comment: string,
  ): Promise<void> => mutate(() => submitPestReport(
    workbenchStore.projectCodeComputed,
    reportCode,
    comment,
    requireUserCode(),
  ))

  const reviewReport = async (
    reportCode: string,
    action: 'approve' | 'return',
    comment: string,
  ): Promise<void> => mutate(() => reviewPestReportApi(
    workbenchStore.projectCodeComputed,
    reportCode,
    action,
    comment,
    requireUserCode(),
  ))

  const downloadReport = async (
    reportCode: string,
    filename: string,
  ): Promise<void> => {
    const blob = await downloadPestReport(
      workbenchStore.projectCodeComputed,
      reportCode,
      requireUserCode(),
    )
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
  }

  return {
    overviewRef,
    loadingRef,
    mutatingRef,
    canManageDevicesComputed,
    canIngestComputed,
    canReportFaultComputed,
    canManageModelsComputed,
    canReviewComputed,
    canDeliverAlertComputed,
    canManageReportsComputed,
    canReviewCountyReportComputed,
    canReviewPrefectureReportComputed,
    canReviewProvinceReportComputed,
    canAnswerConsultationComputed,
    canDownloadReportComputed,
    load,
    registerStation,
    registerDevice,
    ingestTelemetry,
    reportFault,
    resolveFault,
    registerModel,
    submitAssessment,
    reviewAssessment,
    createAlert,
    deliverAlert,
    createReport,
    reviseReport,
    requestConsultation,
    answerConsultation,
    submitReport,
    reviewReport,
    downloadReport,
  }
})
