import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  createGrowthMonitoringRun,
  downloadGrowthMonitoringArtifact,
  getGrowthMonitoringOverview,
} from '@/api/growthMonitoring'
import { useLayerStore } from '@/store/layerStore'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  GrowthArtifactType,
  GrowthMonitoringCreatePayload,
  GrowthMonitoringOverview,
  GrowthMonitoringRun,
} from '@/types/growthMonitoring'

export const useGrowthMonitoringStore = defineStore('growth-monitoring', () => {
  const layerStore = useLayerStore()
  const userStore = useUserStore()
  const workbenchStore = useWorkbenchStore()
  const overviewRef = ref<GrowthMonitoringOverview | null>(null)
  const selectedRunCodeRef = ref<string | null>(null)
  const loadingRef = ref<boolean>(false)
  const generatingRef = ref<boolean>(false)
  const downloadingArtifactRef = ref<string | null>(null)

  const selectedRunComputed = computed<GrowthMonitoringRun | null>(() => (
    overviewRef.value?.runs.find(
      (run) => run.run_code === selectedRunCodeRef.value,
    ) || overviewRef.value?.runs[0] || null
  ))
  const eligibleSourcesComputed = computed(() => (
    overviewRef.value?.sources.filter((source) => source.eligible) || []
  ))
  const canGenerateComputed = computed<boolean>(() => (
    workbenchStore.taskEditableComputed
    && userStore.hasCapability('generate_growth_monitoring')
  ))
  const canDownloadComputed = computed<boolean>(() => (
    userStore.hasCapability('download_growth_monitoring')
  ))

  /** 加载来源、任务和异常区，并同步到独立长势图层。 */
  const load = async (selectedRunCode?: string): Promise<void> => {
    const user = userStore.currentUserComputed
    if (!user || !userStore.hasCapability('view_growth_monitoring')) {
      throw new Error('当前项目身份无权查看作物长势监测')
    }
    loadingRef.value = true
    try {
      const overview = await getGrowthMonitoringOverview(
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
        user.user_code,
        selectedRunCode,
      )
      overviewRef.value = overview
      selectedRunCodeRef.value = overview.selected_run_code
      layerStore.setGrowthFeatures(overview.feature_collection)
      layerStore.setVisibility('growth', Boolean(overview.selected_run_code))
    } finally {
      loadingRef.value = false
    }
  }

  /** 执行真实多时相 NDVI 长势监测并选中新成果。 */
  const generate = async (
    payload: Omit<GrowthMonitoringCreatePayload, 'operator_code'>,
  ): Promise<GrowthMonitoringRun> => {
    const user = userStore.currentUserComputed
    if (!user || !canGenerateComputed.value) {
      throw new Error('当前项目身份或任务状态不允许生成长势监测')
    }
    generatingRef.value = true
    try {
      const run = await createGrowthMonitoringRun(
        { ...payload, operator_code: user.user_code },
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
      )
      await load(run.run_code)
      return run
    } finally {
      generatingRef.value = false
    }
  }

  /** 切换历史长势任务并只显示其异常区。 */
  const selectRun = async (runCode: string): Promise<void> => {
    if (runCode === selectedRunCodeRef.value) return
    await load(runCode)
  }

  /** 下载分级 GeoTIFF 或异常区 GeoJSON。 */
  const download = async (
    run: GrowthMonitoringRun,
    artifact: GrowthArtifactType,
  ): Promise<{ blob: Blob; filename: string }> => {
    const user = userStore.currentUserComputed
    if (!user || !canDownloadComputed.value) {
      throw new Error('当前项目身份无权下载长势监测成果')
    }
    downloadingArtifactRef.value = `${run.run_code}:${artifact}`
    try {
      return {
        blob: await downloadGrowthMonitoringArtifact(
          run.run_code,
          artifact,
          user.user_code,
          workbenchStore.projectCodeComputed,
        ),
        filename: artifact === 'classification'
          ? run.classification_filename
          : run.anomaly_filename,
      }
    } finally {
      downloadingArtifactRef.value = null
    }
  }

  return {
    overviewRef,
    selectedRunCodeRef,
    loadingRef,
    generatingRef,
    downloadingArtifactRef,
    selectedRunComputed,
    eligibleSourcesComputed,
    canGenerateComputed,
    canDownloadComputed,
    load,
    generate,
    selectRun,
    download,
  }
})
