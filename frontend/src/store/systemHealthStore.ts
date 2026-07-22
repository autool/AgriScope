import { defineStore } from 'pinia'
import { ref } from 'vue'

import { getSystemHealth } from '@/api/systemHealth'

export const useSystemHealthStore = defineStore('systemHealth', () => {
  const stateRef = ref<'checking' | 'online' | 'offline'>('checking')
  const lastCheckedAtRef = ref<string | null>(null)
  let timer: ReturnType<typeof window.setInterval> | null = null

  const check = async (): Promise<void> => {
    try {
      const result = await getSystemHealth()
      stateRef.value = result.status === 'ok' && result.database === 'connected'
        ? 'online'
        : 'offline'
    } catch {
      stateRef.value = 'offline'
    } finally {
      lastCheckedAtRef.value = new Date().toISOString()
    }
  }

  const start = (): void => {
    if (timer !== null) return
    void check()
    timer = window.setInterval(() => {
      void check()
    }, 30_000)
  }

  const stop = (): void => {
    if (timer === null) return
    window.clearInterval(timer)
    timer = null
  }

  return { stateRef, lastCheckedAtRef, check, start, stop }
})
