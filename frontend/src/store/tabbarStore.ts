import type { RouteLocationNormalizedLoaded } from 'vue-router'

import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

import { useLayoutStore } from '@/store/layoutStore'

export interface WorkspaceTab {
  path: string
  title: string
  pinned: boolean
}

const STORAGE_KEY = 'remote-sensing-workspace-tabs-v1'
const HOME_PATH = '/interpretation'

const loadTabs = (): WorkspaceTab[] => {
  if (typeof window === 'undefined') return []
  const cached = window.localStorage.getItem(STORAGE_KEY)
  if (!cached) return []
  try {
    const value = JSON.parse(cached) as unknown
    if (!Array.isArray(value)) return []
    return value.filter((item): item is WorkspaceTab => (
      typeof item === 'object'
      && item !== null
      && typeof item.path === 'string'
      && typeof item.title === 'string'
      && typeof item.pinned === 'boolean'
    ))
  } catch (error: unknown) {
    if (error instanceof SyntaxError) {
      window.localStorage.removeItem(STORAGE_KEY)
      return []
    }
    throw error
  }
}

export const useTabbarStore = defineStore('tabbar', () => {
  const layoutStore = useLayoutStore()
  const tabsRef = ref<WorkspaceTab[]>(loadTabs())
  const activePathRef = ref<string>('')

  const visitRoute = (route: RouteLocationNormalizedLoaded): void => {
    const title = typeof route.meta.title === 'string'
      ? route.meta.title
      : String(route.name || route.path)
    activePathRef.value = route.fullPath
    const existing = tabsRef.value.find((tab) => tab.path === route.fullPath)
    if (existing) {
      existing.title = title
      return
    }
    tabsRef.value.push({
      path: route.fullPath,
      title,
      pinned: route.path === HOME_PATH,
    })
  }

  const closeTab = (path: string): string | null => {
    const index = tabsRef.value.findIndex((tab) => tab.path === path)
    if (index < 0 || tabsRef.value[index]?.pinned) return null
    tabsRef.value.splice(index, 1)
    if (activePathRef.value !== path) return null
    const nextTab = tabsRef.value[index] || tabsRef.value[index - 1]
    return nextTab?.path || HOME_PATH
  }

  const closeOtherTabs = (path: string): void => {
    tabsRef.value = tabsRef.value.filter((tab) => tab.pinned || tab.path === path)
  }

  const closeAllTabs = (): string => {
    tabsRef.value = tabsRef.value.filter((tab) => tab.pinned)
    return tabsRef.value[0]?.path || HOME_PATH
  }

  watch(
    tabsRef,
    (tabs) => {
      if (layoutStore.preferencesRef.tabbar.persist) {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(tabs))
      } else {
        window.localStorage.removeItem(STORAGE_KEY)
      }
    },
    { deep: true },
  )

  watch(
    () => layoutStore.preferencesRef.tabbar.persist,
    (persist) => {
      if (persist) {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(tabsRef.value))
      } else {
        window.localStorage.removeItem(STORAGE_KEY)
      }
    },
  )

  return {
    tabsRef,
    activePathRef,
    visitRoute,
    closeTab,
    closeOtherTabs,
    closeAllTabs,
  }
})
