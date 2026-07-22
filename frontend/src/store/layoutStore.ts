import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

export type ContentMode = 'wide' | 'boxed'
export type InterfaceDensity = 'comfortable' | 'compact'

export interface LayoutPreferences {
  app: {
    contentMode: ContentMode
    density: InterfaceDensity
  }
  header: {
    workspaceVisible: boolean
  }
  sidebar: {
    collapsed: boolean
    collapseWidth: number
    width: number
  }
  tabbar: {
    enabled: boolean
    keepAlive: boolean
    persist: boolean
  }
  transition: {
    enabled: boolean
  }
}

type PreferenceSection = keyof LayoutPreferences
type PreferencePatch = {
  [TSection in PreferenceSection]?: Partial<LayoutPreferences[TSection]>
}

const STORAGE_KEY = 'remote-sensing-layout-preferences-v1'

const createDefaultPreferences = (): LayoutPreferences => ({
  app: {
    contentMode: 'wide',
    density: 'comfortable',
  },
  header: {
    workspaceVisible: true,
  },
  sidebar: {
    collapsed: false,
    collapseWidth: 64,
    width: 210,
  },
  tabbar: {
    enabled: true,
    keepAlive: true,
    persist: true,
  },
  transition: {
    enabled: true,
  },
})

const isRecord = (value: unknown): value is Record<string, unknown> => (
  typeof value === 'object' && value !== null && !Array.isArray(value)
)

/**
 * 合并本地偏好与默认值，只接受结构正确的偏好分组。
 * Args:
 *   candidate: localStorage 中读取的未知对象。
 * Returns:
 *   LayoutPreferences: 可安全用于布局渲染的偏好设置。
 */
const normalizePreferences = (candidate: unknown): LayoutPreferences => {
  const defaults = createDefaultPreferences()
  if (!isRecord(candidate)) return defaults
  const app = isRecord(candidate.app) ? candidate.app : {}
  const header = isRecord(candidate.header) ? candidate.header : {}
  const sidebar = isRecord(candidate.sidebar) ? candidate.sidebar : {}
  const tabbar = isRecord(candidate.tabbar) ? candidate.tabbar : {}
  const transition = isRecord(candidate.transition) ? candidate.transition : {}
  return {
    app: {
      contentMode: app.contentMode === 'boxed' ? 'boxed' : defaults.app.contentMode,
      density: app.density === 'compact' ? 'compact' : defaults.app.density,
    },
    header: {
      workspaceVisible: typeof header.workspaceVisible === 'boolean'
        ? header.workspaceVisible
        : defaults.header.workspaceVisible,
    },
    sidebar: {
      collapsed: typeof sidebar.collapsed === 'boolean'
        ? sidebar.collapsed
        : defaults.sidebar.collapsed,
      collapseWidth: typeof sidebar.collapseWidth === 'number'
        ? Math.min(Math.max(sidebar.collapseWidth, 56), 80)
        : defaults.sidebar.collapseWidth,
      width: typeof sidebar.width === 'number'
        ? Math.min(Math.max(sidebar.width, 190), 280)
        : defaults.sidebar.width,
    },
    tabbar: {
      enabled: typeof tabbar.enabled === 'boolean'
        ? tabbar.enabled
        : defaults.tabbar.enabled,
      keepAlive: typeof tabbar.keepAlive === 'boolean'
        ? tabbar.keepAlive
        : defaults.tabbar.keepAlive,
      persist: typeof tabbar.persist === 'boolean'
        ? tabbar.persist
        : defaults.tabbar.persist,
    },
    transition: {
      enabled: typeof transition.enabled === 'boolean'
        ? transition.enabled
        : defaults.transition.enabled,
    },
  }
}

const loadPreferences = (): LayoutPreferences => {
  if (typeof window === 'undefined') return createDefaultPreferences()
  const cached = window.localStorage.getItem(STORAGE_KEY)
  if (!cached) return createDefaultPreferences()
  try {
    return normalizePreferences(JSON.parse(cached))
  } catch (error: unknown) {
    if (error instanceof SyntaxError) {
      window.localStorage.removeItem(STORAGE_KEY)
      return createDefaultPreferences()
    }
    throw error
  }
}

export const useLayoutStore = defineStore('layout', () => {
  const preferencesRef = ref<LayoutPreferences>(loadPreferences())
  const preferencesDrawerOpenRef = ref<boolean>(false)
  const contentMaximizedRef = ref<boolean>(false)
  const routeRefreshKeyRef = ref<number>(0)

  const sidebarWidthComputed = computed<number>(() => (
    preferencesRef.value.sidebar.collapsed
      ? preferencesRef.value.sidebar.collapseWidth
      : preferencesRef.value.sidebar.width
  ))

  const updatePreferences = (patch: PreferencePatch): void => {
    const current = preferencesRef.value
    preferencesRef.value = normalizePreferences({
      app: { ...current.app, ...patch.app },
      header: { ...current.header, ...patch.header },
      sidebar: { ...current.sidebar, ...patch.sidebar },
      tabbar: { ...current.tabbar, ...patch.tabbar },
      transition: { ...current.transition, ...patch.transition },
    })
  }

  const toggleSidebar = (): void => {
    updatePreferences({
      sidebar: { collapsed: !preferencesRef.value.sidebar.collapsed },
    })
  }

  const openPreferences = (): void => {
    preferencesDrawerOpenRef.value = true
  }

  const closePreferences = (): void => {
    preferencesDrawerOpenRef.value = false
  }

  const toggleContentMaximized = (): void => {
    contentMaximizedRef.value = !contentMaximizedRef.value
  }

  const refreshCurrentRoute = (): void => {
    routeRefreshKeyRef.value += 1
  }

  const resetPreferences = (): void => {
    preferencesRef.value = createDefaultPreferences()
  }

  watch(
    preferencesRef,
    (preferences) => {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences))
    },
    { deep: true },
  )

  return {
    preferencesRef,
    preferencesDrawerOpenRef,
    contentMaximizedRef,
    routeRefreshKeyRef,
    sidebarWidthComputed,
    updatePreferences,
    toggleSidebar,
    openPreferences,
    closePreferences,
    toggleContentMaximized,
    refreshCurrentRoute,
    resetPreferences,
  }
})
