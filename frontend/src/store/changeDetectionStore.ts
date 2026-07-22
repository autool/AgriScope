import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  createChangeDetectionRun,
  discoverChangeCandidates,
  getChangeComparisonMetadata,
  getChangeDetectionOverview,
  importChangeCandidates,
  reviewChangeCandidate,
} from '@/api/changeDetection'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  ChangeCandidate,
  ChangeCandidateDiscoveryPayload,
  ChangeCandidateDiscoveryResult,
  ChangeCandidateImportPayload,
  ChangeCandidateImportResult,
  ChangeCandidateReviewPayload,
  ChangeComparisonMetadata,
  ChangeDetectionOverview,
  ChangeDetectionRun,
  ChangeRunCreatePayload,
} from '@/types/changeDetection'

export const useChangeDetectionStore = defineStore('change-detection', () => {
  const workbenchStore = useWorkbenchStore()
  const overviewRef = ref<ChangeDetectionOverview | null>(null)
  const selectedRunCodeRef = ref<string>('')
  const selectedCandidateCodeRef = ref<string>('')
  const loadingRef = ref<boolean>(false)
  const savingRef = ref<boolean>(false)
  const comparisonRef = ref<ChangeComparisonMetadata | null>(null)
  const comparisonLoadingRef = ref<boolean>(false)
  const comparisonErrorRef = ref<string>('')

  const selectedRunComputed = computed<ChangeDetectionRun | null>(() => (
    overviewRef.value?.runs.find(
      (run) => run.run_code === selectedRunCodeRef.value,
    ) || overviewRef.value?.runs[0] || null
  ))

  const selectedCandidateComputed = computed<ChangeCandidate | null>(() => (
    selectedRunComputed.value?.candidates.find(
      (candidate) => candidate.candidate_code === selectedCandidateCodeRef.value,
    ) || null
  ))

  /** 加载变化检测工作台并保持仍存在的当前选择。 */
  const load = async (): Promise<void> => {
    loadingRef.value = true
    try {
      overviewRef.value = await getChangeDetectionOverview(
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
      )
      const selectedRunExists = overviewRef.value.runs.some(
        (run) => run.run_code === selectedRunCodeRef.value,
      )
      if (!selectedRunExists) {
        selectedRunCodeRef.value = overviewRef.value.runs[0]?.run_code || ''
        comparisonRef.value = null
        comparisonErrorRef.value = ''
      }
      const selectedCandidateExists = selectedRunComputed.value?.candidates.some(
        (candidate) => candidate.candidate_code === selectedCandidateCodeRef.value,
      )
      if (!selectedCandidateExists) selectedCandidateCodeRef.value = ''
    } finally {
      loadingRef.value = false
    }
  }

  /** 选择检测任务并清空跨任务候选选择。 */
  const selectRun = (runCode: string): void => {
    const runChanged = selectedRunCodeRef.value !== runCode
    selectedRunCodeRef.value = runCode
    selectedCandidateCodeRef.value = ''
    if (runChanged) {
      comparisonRef.value = null
      comparisonErrorRef.value = ''
    }
  }

  /** 选择候选图斑。 */
  const selectCandidate = (candidateCode: string): void => {
    selectedCandidateCodeRef.value = candidateCode
  }

  /** 创建变化检测任务并选中新任务。 */
  const createRun = async (payload: ChangeRunCreatePayload): Promise<void> => {
    savingRef.value = true
    try {
      const run = await createChangeDetectionRun(
        payload,
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
      )
      await load()
      selectRun(run.run_code)
    } finally {
      savingRef.value = false
    }
  }

  /** 导入候选后刷新当前任务队列。 */
  const importCandidates = async (
    runCode: string,
    payload: ChangeCandidateImportPayload,
  ): Promise<ChangeCandidateImportResult> => {
    savingRef.value = true
    try {
      const result = await importChangeCandidates(
        runCode,
        payload,
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
      )
      await load()
      selectRun(runCode)
      return result
    } finally {
      savingRef.value = false
    }
  }

  /** 运行内置差分算法后刷新未分类候选队列。 */
  const discoverCandidates = async (
    runCode: string,
    payload: ChangeCandidateDiscoveryPayload,
  ): Promise<ChangeCandidateDiscoveryResult> => {
    savingRef.value = true
    try {
      const result = await discoverChangeCandidates(
        runCode,
        payload,
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
      )
      await load()
      selectRun(runCode)
      return result
    } finally {
      savingRef.value = false
    }
  }

  /** 保存人工判读结论并保持候选选择。 */
  const reviewCandidate = async (
    runCode: string,
    candidateCode: string,
    payload: ChangeCandidateReviewPayload,
  ): Promise<void> => {
    savingRef.value = true
    try {
      await reviewChangeCandidate(
        runCode,
        candidateCode,
        payload,
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
      )
      await load()
      selectRun(runCode)
      selectCandidate(candidateCode)
    } finally {
      savingRef.value = false
    }
  }

  /** 加载两期真实栅格公共网格预览，失败时保留可恢复错误状态。 */
  const loadComparison = async (runCode: string): Promise<void> => {
    comparisonLoadingRef.value = true
    comparisonErrorRef.value = ''
    comparisonRef.value = null
    try {
      comparisonRef.value = await getChangeComparisonMetadata(
        runCode,
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
      )
    } catch (error) {
      comparisonErrorRef.value = error instanceof Error
        ? error.message
        : '双时相影像预览加载失败'
    } finally {
      comparisonLoadingRef.value = false
    }
  }

  return {
    overviewRef,
    selectedRunCodeRef,
    selectedCandidateCodeRef,
    selectedRunComputed,
    selectedCandidateComputed,
    loadingRef,
    savingRef,
    comparisonRef,
    comparisonLoadingRef,
    comparisonErrorRef,
    load,
    selectRun,
    selectCandidate,
    createRun,
    importCandidates,
    discoverCandidates,
    reviewCandidate,
    loadComparison,
  }
})
