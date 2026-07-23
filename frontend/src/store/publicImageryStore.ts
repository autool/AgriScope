import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { importPublicImagery, searchPublicImagery } from '@/api/publicImagery'
import { useAssetStore } from '@/store/assetStore'
import { useImageryHistoryStore } from '@/store/imageryHistoryStore'
import { useMapStore } from '@/store/mapStore'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  PublicImageryCandidate,
  PublicImageryImportResponse,
  PublicImagerySearchRequest,
  PublicImagerySearchResponse,
} from '@/types/publicImagery'

export const usePublicImageryStore = defineStore('publicImagery', () => {
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
  const selectedItemIdRef = ref<string>('')
  const searchingRef = ref<boolean>(false)
  const importingRef = ref<boolean>(false)
  const errorRef = ref<string | null>(null)
  const lastImportRef = ref<PublicImageryImportResponse | null>(null)
  const canImportComputed = computed<boolean>(() => (
    userStore.hasCapability('manage_imagery')
  ))
  const selectedCandidateComputed = computed<PublicImageryCandidate | null>(() => (
    resultRef.value?.items.find(item => item.item_id === selectedItemIdRef.value)
    || null
  ))

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
      selectedItemIdRef.value = (
        resultRef.value.items.find(item => item.fully_covers_query)?.item_id
        || resultRef.value.items[0]?.item_id
        || ''
      )
    } catch (error) {
      errorRef.value = error instanceof Error
        ? error.message
        : '公开历史影像检索失败'
      throw error
    } finally {
      searchingRef.value = false
    }
  }

  /** 导入选中候选并刷新影像目录、覆盖矩阵和项目总览。 */
  const importSelected = async (
    assetCode: string,
    assetName: string,
  ): Promise<PublicImageryImportResponse> => {
    const user = userStore.currentUserComputed
    const candidate = selectedCandidateComputed.value
    if (!user || !canImportComputed.value) {
      throw new Error('当前项目身份无权导入公开影像')
    }
    if (!candidate || !candidate.fully_covers_query) {
      throw new Error('请选择完整覆盖当前 WGS84 范围的候选')
    }
    importingRef.value = true
    errorRef.value = null
    try {
      const response = await importPublicImagery({
        project_code: workbenchStore.projectCodeComputed,
        task_code: workbenchStore.taskCodeComputed,
        item_id: candidate.item_id,
        bbox: [...queryRef.value.bbox],
        asset_code: assetCode,
        asset_name: assetName,
        operator_code: user.user_code,
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
    selectedItemIdRef,
    selectedCandidateComputed,
    searchingRef,
    importingRef,
    errorRef,
    lastImportRef,
    canImportComputed,
    resetBboxFromCurrentView,
    search,
    importSelected,
  }
})
