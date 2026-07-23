import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  createThematicMapTemplate,
  generateThematicMapAtlas,
  generateThematicMapProducts,
  getThematicMapOverview,
} from '@/api/thematicMap'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  ThematicMapAtlas,
  ThematicMapAtlasGeneratePayload,
  ThematicMapBatchGeneratePayload,
  ThematicMapOverview,
  ThematicMapProduct,
  ThematicMapTemplateCreatePayload,
} from '@/types/thematicMap'

export const useThematicMapStore = defineStore('thematicMap', () => {
  const workbenchStore = useWorkbenchStore()
  const userStore = useUserStore()
  const overviewRef = ref<ThematicMapOverview | null>(null)
  const loadingRef = ref<boolean>(false)
  const savingTemplateRef = ref<boolean>(false)
  const generatingRef = ref<boolean>(false)
  const generatingAtlasRef = ref<boolean>(false)
  const canManageComputed = computed<boolean>(() => (
    userStore.hasCapability('manage_thematic_maps')
  ))
  const canGenerateComputed = computed<boolean>(() => (
    userStore.hasCapability('generate_thematic_maps')
  ))
  const canDownloadComputed = computed<boolean>(() => (
    userStore.hasCapability('download_thematic_maps')
  ))
  const canViewComputed = computed<boolean>(() => (
    userStore.hasCapability('view_thematic_maps')
  ))

  const load = async (): Promise<void> => {
    loadingRef.value = true
    try {
      overviewRef.value = await getThematicMapOverview(
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
      )
    } finally {
      loadingRef.value = false
    }
  }

  const createTemplate = async (
    payload: Omit<ThematicMapTemplateCreatePayload, 'operator_code'>,
  ): Promise<void> => {
    const user = userStore.currentUserComputed
    if (!user || !canManageComputed.value) {
      throw new Error('当前项目身份无权创建专题图模板')
    }
    savingTemplateRef.value = true
    try {
      await createThematicMapTemplate(
        { ...payload, operator_code: user.user_code },
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
      )
      await load()
    } finally {
      savingTemplateRef.value = false
    }
  }

  const generate = async (
    payload: Omit<ThematicMapBatchGeneratePayload, 'operator_code'>,
  ): Promise<number> => {
    const user = userStore.currentUserComputed
    if (!user || !canGenerateComputed.value) {
      throw new Error('当前项目身份无权生成专题图成果')
    }
    generatingRef.value = true
    try {
      const result = await generateThematicMapProducts(
        { ...payload, operator_code: user.user_code },
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
      )
      await load()
      return result.generated_count
    } finally {
      generatingRef.value = false
    }
  }

  const generateAtlas = async (
    payload: Omit<ThematicMapAtlasGeneratePayload, 'operator_code'>,
  ): Promise<ThematicMapAtlas> => {
    const user = userStore.currentUserComputed
    if (!user || !canGenerateComputed.value) {
      throw new Error('当前项目身份无权生成专题图集')
    }
    generatingAtlasRef.value = true
    try {
      const result = await generateThematicMapAtlas(
        { ...payload, operator_code: user.user_code },
        workbenchStore.projectCodeComputed,
        workbenchStore.taskCodeComputed,
      )
      await load()
      return result.atlas
    } finally {
      generatingAtlasRef.value = false
    }
  }

  const productUrl = (
    product: ThematicMapProduct,
    disposition: 'inline' | 'attachment',
  ): string | null => {
    const user = userStore.currentUserComputed
    if (!user) return null
    if (disposition === 'inline' && !canViewComputed.value) return null
    if (disposition === 'attachment' && !canDownloadComputed.value) return null
    const params = new URLSearchParams({
      operator_code: user.user_code,
      disposition,
    })
    return `${product.download_url}?${params.toString()}`
  }

  const atlasUrl = (atlas: ThematicMapAtlas): string | null => {
    const user = userStore.currentUserComputed
    if (!user || !canDownloadComputed.value || !atlas.download_url) return null
    const params = new URLSearchParams({ operator_code: user.user_code })
    return `${atlas.download_url}?${params.toString()}`
  }

  return {
    overviewRef,
    loadingRef,
    savingTemplateRef,
    generatingRef,
    generatingAtlasRef,
    canManageComputed,
    canGenerateComputed,
    canDownloadComputed,
    canViewComputed,
    load,
    createTemplate,
    generate,
    generateAtlas,
    productUrl,
    atlasUrl,
  }
})
