import { defineStore } from 'pinia'
import { ref } from 'vue'

import { executeReviewAction, rollbackPlotVersion } from '@/api/index'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'

export const useReviewStore = defineStore('review', () => {
  const workbenchStore = useWorkbenchStore()
  const userStore = useUserStore()
  const loadingRef = ref<boolean>(false)

  const requireCurrentUserCode = (): string => {
    const userCode = userStore.currentUserComputed?.user_code
    if (!userCode) throw new Error('当前项目用户尚未加载')
    return userCode
  }

  /**
   * 执行三级审核动作。
   * Args:
   *   action: 通过、退回或驳回。
   *   comment: 审核意见。
   *   issueType: 问题类型。
   * Returns:
   *   Promise<void>: 审核状态刷新完成后结束。
   */
  const executeAction = async (
    action: 'pass' | 'return' | 'reject',
    comment: string,
    issueType: string,
  ): Promise<void> => {
    loadingRef.value = true
    try {
      await executeReviewAction(workbenchStore.taskCodeComputed, {
        action,
        reviewer_code: requireCurrentUserCode(),
        comment,
        issue_type: action === 'pass' ? null : issueType,
      })
      await workbenchStore.refreshOverview()
    } finally {
      loadingRef.value = false
    }
  }

  /**
   * 恢复当前图斑历史版本。
   * Args:
   *   targetVersion: 目标历史版本。
   * Returns:
   *   Promise<void>: 图斑版本和任务状态刷新完成后结束。
   */
  const rollback = async (targetVersion: number): Promise<void> => {
    const plotCode = workbenchStore.selectedPlotCodeComputed
    if (!plotCode) return
    await rollbackPlotVersion(
      plotCode,
      {
        target_version: targetVersion,
        operator_code: requireCurrentUserCode(),
        comment: `审核复核后恢复至 v${targetVersion}`,
      },
      workbenchStore.taskCodeComputed,
    )
    await Promise.all([
      workbenchStore.loadSelectedPlot(plotCode),
      workbenchStore.refreshOverview(),
    ])
  }

  return { loadingRef, executeAction, rollback }
})
