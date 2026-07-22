import { defineStore } from 'pinia'
import { ref } from 'vue'

import {
  createSupervisionFinding,
  createSupervisionInspection,
  createSupervisionPlan,
  evaluateSupervisionCounty,
  generateSupervisionReport,
  getSupervisionOverview,
  getSupervisionSamples,
  reinspectSupervisionFinding,
  submitSupervisionRectification,
} from '@/api/supervision'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  SupervisionCountyEvaluationPayload,
  SupervisionFindingCreatePayload,
  SupervisionInspectionCreatePayload,
  SupervisionOverview,
  SupervisionPlanCreatePayload,
  SupervisionRectificationPayload,
  SupervisionReinspectionPayload,
  SupervisionReport,
  SupervisionReportGeneratePayload,
  SupervisionSamplePage,
} from '@/types/supervision'

export const useSupervisionStore = defineStore('supervision', () => {
  const workbenchStore = useWorkbenchStore()
  const overviewRef = ref<SupervisionOverview | null>(null)
  const samplePageRef = ref<SupervisionSamplePage | null>(null)
  const loadingRef = ref<boolean>(false)
  const samplesLoadingRef = ref<boolean>(false)
  const savingRef = ref<boolean>(false)

  /** 加载独立监理工作区和证据聚合。 */
  const load = async (): Promise<void> => {
    loadingRef.value = true
    try {
      overviewRef.value = await getSupervisionOverview(
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
      )
    } finally {
      loadingRef.value = false
    }
  }

  /** 加载计划显式样本分页。 */
  const loadSamples = async (
    planCode: string,
    page: number = 1,
    pageSize: number = 50,
    regionCode: string | null = null,
  ): Promise<void> => {
    samplesLoadingRef.value = true
    try {
      samplePageRef.value = await getSupervisionSamples(
        planCode,
        page,
        pageSize,
        regionCode,
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
      )
    } finally {
      samplesLoadingRef.value = false
    }
  }

  /** 执行写操作并刷新监理聚合状态。 */
  const mutateAndReload = async <T>(operation: () => Promise<T>): Promise<T> => {
    savingRef.value = true
    try {
      const result = await operation()
      await load()
      return result
    } finally {
      savingRef.value = false
    }
  }

  const createPlan = (payload: SupervisionPlanCreatePayload): Promise<void> => (
    mutateAndReload(async () => {
      await createSupervisionPlan(
        payload,
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
      )
    })
  )

  const createInspection = (
    planCode: string,
    payload: SupervisionInspectionCreatePayload,
  ): Promise<void> => mutateAndReload(async () => {
    await createSupervisionInspection(
      planCode,
      payload,
      workbenchStore.projectCodeComputed,
      workbenchStore.taskCodeComputed,
    )
  })

  const createFinding = (
    planCode: string,
    inspectionCode: string,
    payload: SupervisionFindingCreatePayload,
  ): Promise<void> => mutateAndReload(async () => {
    await createSupervisionFinding(
      planCode,
      inspectionCode,
      payload,
      workbenchStore.projectCodeComputed,
      workbenchStore.taskCodeComputed,
    )
  })

  const submitRectification = (
    planCode: string,
    findingCode: string,
    payload: SupervisionRectificationPayload,
  ): Promise<void> => mutateAndReload(async () => {
    await submitSupervisionRectification(
      planCode,
      findingCode,
      payload,
      workbenchStore.projectCodeComputed,
      workbenchStore.taskCodeComputed,
    )
  })

  const reinspectFinding = (
    planCode: string,
    findingCode: string,
    payload: SupervisionReinspectionPayload,
  ): Promise<void> => mutateAndReload(async () => {
    await reinspectSupervisionFinding(
      planCode,
      findingCode,
      payload,
      workbenchStore.projectCodeComputed,
      workbenchStore.taskCodeComputed,
    )
  })

  const evaluateCounty = (
    planCode: string,
    regionCode: string,
    payload: SupervisionCountyEvaluationPayload,
  ): Promise<void> => mutateAndReload(async () => {
    await evaluateSupervisionCounty(
      planCode,
      regionCode,
      payload,
      workbenchStore.projectCodeComputed,
      workbenchStore.taskCodeComputed,
    )
  })

  const generateReport = (
    planCode: string,
    payload: SupervisionReportGeneratePayload,
  ): Promise<SupervisionReport> => mutateAndReload(() => (
    generateSupervisionReport(
      planCode,
      payload,
      workbenchStore.projectCodeComputed,
      workbenchStore.taskCodeComputed,
    )
  ))

  return {
    overviewRef,
    samplePageRef,
    loadingRef,
    samplesLoadingRef,
    savingRef,
    load,
    loadSamples,
    createPlan,
    createInspection,
    createFinding,
    submitRectification,
    reinspectFinding,
    evaluateCounty,
    generateReport,
  }
})
