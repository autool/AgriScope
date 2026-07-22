import { defineStore } from 'pinia'
import { ref } from 'vue'

import { getImageryHistoryOverview } from '@/api/imageryHistory'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type { ImageryHistoryOverview } from '@/types/imageryHistory'

export const useImageryHistoryStore = defineStore('imageryHistory', () => {
  const workbenchStore = useWorkbenchStore()
  const overviewRef = ref<ImageryHistoryOverview | null>(null)
  const loadingRef = ref<boolean>(false)
  const errorRef = ref<string | null>(null)

  const load = async (): Promise<void> => {
    loadingRef.value = true
    errorRef.value = null
    try {
      overviewRef.value = await getImageryHistoryOverview(
        workbenchStore.projectCodeComputed,
      )
    } catch (error) {
      errorRef.value = '历史影像覆盖矩阵加载失败，请检查后端服务和数据状态'
      throw error
    } finally {
      loadingRef.value = false
    }
  }

  return {
    overviewRef,
    loadingRef,
    errorRef,
    load,
  }
})
