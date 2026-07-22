import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  getWorkbenchQualityIssues,
  resolveWorkbenchQualityIssue,
} from '@/api/index'
import type {
  QualityIssueList,
  QualityIssueQuery,
  QualityIssueResolveResult,
} from '@/types/workbench'

const createDefaultQuery = (): QualityIssueQuery => ({
  status: 'open',
  page: 1,
  page_size: 10,
})

export const useQualityIssueStore = defineStore('qualityIssue', () => {
  const taskCodeRef = ref<string>('RS-2026-045')
  const queryRef = ref<QualityIssueQuery>(createDefaultQuery())
  const resultRef = ref<QualityIssueList | null>(null)
  const loadingRef = ref<boolean>(false)
  const errorRef = ref<string | null>(null)
  const resolvingIssueIdRef = ref<number | null>(null)
  let requestSequence = 0

  const itemsComputed = computed(() => resultRef.value?.items || [])
  const ruleOptionsComputed = computed(() => (
    resultRef.value?.rule_counts.map((item) => ({
      value: item.rule_code,
      label: `${item.rule_label} · ${item.open_count}`,
    })) || []
  ))

  /**
   * 按当前筛选条件加载任务质量问题。
   * Args:
   *   taskCode: 作业任务编号。
   * Returns:
   *   Promise<void>: 最新请求完成后结束。
   */
  const load = async (taskCode: string = taskCodeRef.value): Promise<void> => {
    taskCodeRef.value = taskCode
    const sequence = ++requestSequence
    loadingRef.value = true
    errorRef.value = null
    try {
      const result = await getWorkbenchQualityIssues(taskCode, queryRef.value)
      if (sequence === requestSequence) resultRef.value = result
    } catch (error) {
      if (sequence === requestSequence) {
        errorRef.value = error instanceof Error ? error.message : '问题列表加载失败'
      }
    } finally {
      if (sequence === requestSequence) loadingRef.value = false
    }
  }

  /**
   * 更新筛选条件并从第一页重新查询。
   * Args:
   *   patch: 一个或多个筛选字段。
   * Returns:
   *   Promise<void>: 筛选结果加载完成后结束。
   */
  const updateFilters = async (
    patch: Partial<QualityIssueQuery>,
  ): Promise<void> => {
    queryRef.value = {
      ...queryRef.value,
      ...patch,
      page: 1,
    }
    await load()
  }

  /**
   * 切换问题列表页码。
   * Args:
   *   page: 目标页码。
   * Returns:
   *   Promise<void>: 当前页加载完成后结束。
   */
  const setPage = async (page: number): Promise<void> => {
    queryRef.value = { ...queryRef.value, page }
    await load()
  }

  /**
   * 确认关闭人工审核问题并刷新当前页。
   * Args:
   *   issueId: 问题主键。
   *   operatorCode: 当前项目用户编码。
   *   comment: 整改确认依据。
   * Returns:
   *   Promise<QualityIssueResolveResult>: 问题关闭审计结果。
   */
  const resolveReviewIssue = async (
    issueId: number,
    operatorCode: string,
    comment: string,
  ): Promise<QualityIssueResolveResult> => {
    resolvingIssueIdRef.value = issueId
    try {
      const result = await resolveWorkbenchQualityIssue(
        taskCodeRef.value,
        issueId,
        { operator_code: operatorCode, comment },
      )
      await load()
      return result
    } finally {
      resolvingIssueIdRef.value = null
    }
  }

  return {
    taskCodeRef,
    queryRef,
    resultRef,
    loadingRef,
    errorRef,
    resolvingIssueIdRef,
    itemsComputed,
    ruleOptionsComputed,
    load,
    updateFilters,
    setPage,
    resolveReviewIssue,
  }
})
