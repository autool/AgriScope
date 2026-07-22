import { defineStore } from 'pinia'
import { ref } from 'vue'

import { generateDeliveryPackage, getDeliveryPackages } from '@/api/index'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type { DeliveryList, DeliveryPackage } from '@/types/workbench'

export const useDeliveryStore = defineStore('delivery', () => {
  const workbenchStore = useWorkbenchStore()
  const userStore = useUserStore()
  const deliveriesRef = ref<DeliveryList | null>(null)
  const loadingRef = ref<boolean>(false)

  /**
   * 加载成果交付条件和版本列表。
   * Args:
   *   无。
   * Returns:
   *   Promise<void>: 成果包列表加载完成后结束。
   */
  const load = async (): Promise<void> => {
    loadingRef.value = true
    try {
      deliveriesRef.value = await getDeliveryPackages(
        workbenchStore.taskCodeComputed,
      )
    } finally {
      loadingRef.value = false
    }
  }

  /**
   * 生成新版本成果交付包。
   * Args:
   *   packageName: 成果包名称。
   * Returns:
   *   Promise<DeliveryPackage>: 新生成成果包。
   */
  const generate = async (packageName: string): Promise<DeliveryPackage> => {
    const userCode = userStore.currentUserComputed?.user_code
    if (!userCode) throw new Error('当前项目用户尚未加载')
    const packageData = await generateDeliveryPackage(
      { operator_code: userCode, package_name: packageName },
      workbenchStore.taskCodeComputed,
    )
    await Promise.all([load(), workbenchStore.refreshOverview()])
    return packageData
  }

  return { deliveriesRef, loadingRef, load, generate }
})
