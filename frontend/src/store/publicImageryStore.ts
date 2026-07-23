import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { importPublicImageryBatch, searchPublicImagery } from '@/api/publicImagery'
import { useAssetStore } from '@/store/assetStore'
import { useImageryHistoryStore } from '@/store/imageryHistoryStore'
import { useMapStore } from '@/store/mapStore'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  PublicImageryCandidate,
  PublicImageryBatchDraft,
  PublicImageryBatchImportResponse,
  PublicImagerySearchRequest,
  PublicImagerySearchResponse,
} from '@/types/publicImagery'

export const usePublicImageryStore = defineStore('publicImagery', () => {
  const MAX_SELECTED_ITEMS = 10
  const assetStore = useAssetStore()
  const historyStore = useImageryHistoryStore()
  const mapStore = useMapStore()
  const userStore = useUserStore()
  const workbenchStore = useWorkbenchStore()
  const queryRef = ref<PublicImagerySearchRequest>({
    bbox: [127.45, 47.6, 127.75, 47.8],
    start_date: '1984-01-01',
    end_date: '1990-12-31',
    max_cloud_cover: 15,
  })
  const resultRef = ref<PublicImagerySearchResponse | null>(null)
  const selectedItemIdsRef = ref<string[]>([])
  const assetDraftsRef = ref<Record<string, PublicImageryBatchDraft>>({})
  const batchCodeRef = ref<string>('')
  const batchCommentRef = ref<string>('')
  const searchingRef = ref<boolean>(false)
  const importingRef = ref<boolean>(false)
  const errorRef = ref<string | null>(null)
  const lastImportRef = ref<PublicImageryBatchImportResponse | null>(null)
  const canImportComputed = computed<boolean>(() => (
    userStore.hasCapability('manage_imagery')
  ))
  const selectedCandidatesComputed = computed<PublicImageryCandidate[]>(() => (
    resultRef.value?.items.filter(
      item => selectedItemIdsRef.value.includes(item.item_id),
    ) || []
  ))
  const validationMessagesComputed = computed<string[]>(() => {
    const messages: string[] = []
    if (!canImportComputed.value) messages.push('当前项目身份无权导入公开影像')
    if (selectedCandidatesComputed.value.length === 0) {
      messages.push('请至少选择一景完整覆盖当前范围的候选')
    }
    if (selectedCandidatesComputed.value.length > MAX_SELECTED_ITEMS) {
      messages.push(`单批最多选择 ${MAX_SELECTED_ITEMS} 景公开影像`)
    }
    if (!/^[A-Za-z0-9_-]{1,90}$/.test(batchCodeRef.value.trim())) {
      messages.push('批次编号仅允许字母、数字、下划线和连字符')
    }
    if (batchCommentRef.value.trim().length < 10) {
      messages.push('入库依据至少填写 10 个字符')
    }
    const drafts = selectedCandidatesComputed.value.map(
      candidate => assetDraftsRef.value[candidate.item_id],
    )
    if (drafts.some(draft => !draft)) {
      messages.push('所选候选缺少资产清单')
      return messages
    }
    const assetCodes = drafts.map(draft => draft.asset_code.trim())
    if (assetCodes.some(code => !/^[A-Za-z0-9_-]{1,80}$/.test(code))) {
      messages.push('每个资产编号均须符合编号格式')
    }
    if (new Set(assetCodes).size !== assetCodes.length) {
      messages.push('批次内资产编号不得重复')
    }
    if (drafts.some(draft => !draft.asset_name.trim())) {
      messages.push('每景影像均须填写资产名称')
    }
    if (drafts.some(draft => draft.asset_name.trim().length > 200)) {
      messages.push('资产名称不得超过 200 个字符')
    }
    return messages
  })
  const canSubmitBatchComputed = computed<boolean>(() => (
    !importingRef.value && validationMessagesComputed.value.length === 0
  ))

  const platformLabel = (value: string): string => (
    value.split('-').map(part => (
      part.toLowerCase() === 'landsat' ? 'Landsat' : part.toUpperCase()
    )).join('-')
  )

  /** 为公开候选生成可编辑且稳定的资产清单默认值。 */
  const ensureAssetDraft = (candidate: PublicImageryCandidate): void => {
    if (assetDraftsRef.value[candidate.item_id]) return
    const dateCode = candidate.acquired_at.slice(0, 10).replaceAll('-', '')
    const pathCode = candidate.wrs_path === null
      ? 'PXXX'
      : `P${String(candidate.wrs_path).padStart(3, '0')}`
    const rowCode = candidate.wrs_row === null
      ? 'RXXX'
      : `R${String(candidate.wrs_row).padStart(3, '0')}`
    assetDraftsRef.value[candidate.item_id] = {
      asset_code: `LS_${dateCode}_${pathCode}_${rowCode}`,
      asset_name: `${candidate.acquired_at.slice(0, 10)} ${platformLabel(candidate.platform)} ${pathCode}/${rowCode} 公开历史地表反射率`,
    }
  }

  /** 生成不承载业务事实的唯一批次编号。 */
  const createBatchCode = (): string => {
    const now = new Date()
    const timestamp = [
      now.getFullYear(),
      String(now.getMonth() + 1).padStart(2, '0'),
      String(now.getDate()).padStart(2, '0'),
      String(now.getHours()).padStart(2, '0'),
      String(now.getMinutes()).padStart(2, '0'),
      String(now.getSeconds()).padStart(2, '0'),
    ].join('')
    const random = crypto.randomUUID().replaceAll('-', '').slice(0, 6).toUpperCase()
    return `IMB-LANDSAT-${timestamp}-${random}`
  }

  /** 将检索窗口重置到 mapStore 当前 WGS84 中心附近。 */
  const resetBboxFromCurrentView = (): void => {
    const [longitude, latitude] = mapStore.centerRef
    queryRef.value.bbox = [
      Number((longitude - 0.15).toFixed(6)),
      Number((latitude - 0.1).toFixed(6)),
      Number((longitude + 0.15).toFixed(6)),
      Number((latitude + 0.1).toFixed(6)),
    ]
  }

  /** 检索公开 Landsat 历史候选并优先选择完整覆盖条目。 */
  const search = async (): Promise<void> => {
    searchingRef.value = true
    errorRef.value = null
    lastImportRef.value = null
    try {
      resultRef.value = await searchPublicImagery(queryRef.value)
      assetDraftsRef.value = {}
      batchCodeRef.value = createBatchCode()
      batchCommentRef.value = ''
      const firstComplete = resultRef.value.items.find(
        item => item.fully_covers_query,
      )
      selectedItemIdsRef.value = firstComplete ? [firstComplete.item_id] : []
      if (firstComplete) ensureAssetDraft(firstComplete)
    } catch (error) {
      errorRef.value = error instanceof Error
        ? error.message
        : '公开历史影像检索失败'
      throw error
    } finally {
      searchingRef.value = false
    }
  }

  /** 切换一个完整覆盖候选，严格限制公开批次最多十景。 */
  const toggleCandidate = (itemId: string): void => {
    const candidate = resultRef.value?.items.find(item => item.item_id === itemId)
    if (!candidate?.fully_covers_query) {
      throw new Error('仅可选择完整覆盖当前 WGS84 范围的候选')
    }
    if (selectedItemIdsRef.value.includes(itemId)) {
      selectedItemIdsRef.value = selectedItemIdsRef.value.filter(
        selectedId => selectedId !== itemId,
      )
      return
    }
    if (selectedItemIdsRef.value.length >= MAX_SELECTED_ITEMS) {
      throw new Error(`单批最多选择 ${MAX_SELECTED_ITEMS} 景公开影像`)
    }
    ensureAssetDraft(candidate)
    selectedItemIdsRef.value = [...selectedItemIdsRef.value, itemId]
  }

  /** 一次提交全部候选并刷新影像目录、覆盖矩阵和项目总览。 */
  const importSelectedBatch = async (): Promise<PublicImageryBatchImportResponse> => {
    const user = userStore.currentUserComputed
    if (!user || !canImportComputed.value) {
      throw new Error('当前项目身份无权导入公开影像')
    }
    if (validationMessagesComputed.value.length) {
      throw new Error(validationMessagesComputed.value[0])
    }
    importingRef.value = true
    errorRef.value = null
    try {
      const response = await importPublicImageryBatch({
        project_code: workbenchStore.projectCodeComputed,
        task_code: workbenchStore.taskCodeComputed,
        operator_code: user.user_code,
        batch_code: batchCodeRef.value.trim(),
        comment: batchCommentRef.value.trim(),
        bbox: [...queryRef.value.bbox],
        items: selectedCandidatesComputed.value.map(candidate => ({
          item_id: candidate.item_id,
          asset_code: assetDraftsRef.value[candidate.item_id].asset_code.trim(),
          asset_name: assetDraftsRef.value[candidate.item_id].asset_name.trim(),
        })),
      })
      lastImportRef.value = response
      await Promise.all([
        assetStore.load(),
        historyStore.load(),
        workbenchStore.refreshOverview(),
      ])
      return response
    } catch (error) {
      errorRef.value = error instanceof Error
        ? error.message
        : '公开历史影像导入失败'
      throw error
    } finally {
      importingRef.value = false
    }
  }

  return {
    queryRef,
    resultRef,
    selectedItemIdsRef,
    selectedCandidatesComputed,
    assetDraftsRef,
    batchCodeRef,
    batchCommentRef,
    searchingRef,
    importingRef,
    errorRef,
    lastImportRef,
    canImportComputed,
    validationMessagesComputed,
    canSubmitBatchComputed,
    maxSelectedItems: MAX_SELECTED_ITEMS,
    resetBboxFromCurrentView,
    search,
    toggleCandidate,
    importSelectedBatch,
  }
})
