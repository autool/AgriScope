import { defineStore } from 'pinia'
import { ref } from 'vue'

import { getRuleConfig, updateRuleConfig } from '@/api/index'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type { RuleConfig, RuleConfigUpdatePayload } from '@/types/workbench'

export const useRuleConfigStore = defineStore('ruleConfig', () => {
  const workbenchStore = useWorkbenchStore()
  const configRef = ref<RuleConfig | null>(null)
  const loadingRef = ref<boolean>(false)
  const savingRef = ref<boolean>(false)

  /**
   * 加载当前项目规则配置。
   * Args:
   *   无。
   * Returns:
   *   Promise<void>: 规则配置加载完成后结束。
   */
  const load = async (): Promise<void> => {
    loadingRef.value = true
    try {
      configRef.value = await getRuleConfig(workbenchStore.projectCodeComputed)
    } finally {
      loadingRef.value = false
    }
  }

  /**
   * 保存当前项目规则配置。
   * Args:
   *   payload: 阈值和操作人。
   * Returns:
   *   Promise<RuleConfig>: 后端确认的当前规则。
   */
  const save = async (
    payload: RuleConfigUpdatePayload,
  ): Promise<RuleConfig> => {
    savingRef.value = true
    try {
      const config = await updateRuleConfig(
        payload,
        workbenchStore.projectCodeComputed,
      )
      configRef.value = config
      return config
    } finally {
      savingRef.value = false
    }
  }

  return {
    configRef,
    loadingRef,
    savingRef,
    load,
    save,
  }
})
