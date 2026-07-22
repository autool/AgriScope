import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  createImageryRegistrationJob,
  downloadImageryRegistrationJob,
  getImageryRegistrationOverview,
} from '@/api/imageryRegistration'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  ImageryRegistrationCreatePayload,
  ImageryRegistrationOverview,
} from '@/types/imageryRegistration'

export const useImageryRegistrationStore = defineStore(
  'imageryRegistration',
  () => {
    const userStore = useUserStore()
    const workbenchStore = useWorkbenchStore()
    const overviewRef = ref<ImageryRegistrationOverview | null>(null)
    const loadingRef = ref<boolean>(false)
    const creatingRef = ref<boolean>(false)
    const downloadingJobCodeRef = ref<string | null>(null)
    const canProcessComputed = computed<boolean>(() => (
      userStore.hasCapability('process_imagery')
    ))

    const requireUserCode = (): string => {
      const userCode = userStore.currentUserComputed?.user_code
      if (!userCode || !canProcessComputed.value) {
        throw new Error('当前项目身份无权执行影像自动配准')
      }
      return userCode
    }

    const load = async (): Promise<void> => {
      loadingRef.value = true
      try {
        await userStore.initialize(workbenchStore.projectCodeComputed)
        overviewRef.value = await getImageryRegistrationOverview(
          workbenchStore.projectCodeComputed,
          requireUserCode(),
        )
      } finally {
        loadingRef.value = false
      }
    }

    const createJob = async (
      payload: Omit<ImageryRegistrationCreatePayload, 'operator_code'>,
    ): Promise<void> => {
      creatingRef.value = true
      try {
        await userStore.initialize(workbenchStore.projectCodeComputed)
        await createImageryRegistrationJob(
          workbenchStore.projectCodeComputed,
          workbenchStore.taskCodeComputed,
          { ...payload, operator_code: requireUserCode() },
        )
        await load()
        await workbenchStore.refreshOverview()
      } finally {
        creatingRef.value = false
      }
    }

    const downloadJob = async (
      jobCode: string,
      filename: string,
    ): Promise<void> => {
      downloadingJobCodeRef.value = jobCode
      try {
        await userStore.initialize(workbenchStore.projectCodeComputed)
        const blob = await downloadImageryRegistrationJob(
          workbenchStore.projectCodeComputed,
          jobCode,
          requireUserCode(),
        )
        const url = URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.download = filename
        link.click()
        URL.revokeObjectURL(url)
      } finally {
        downloadingJobCodeRef.value = null
      }
    }

    return {
      overviewRef,
      loadingRef,
      creatingRef,
      downloadingJobCodeRef,
      canProcessComputed,
      load,
      createJob,
      downloadJob,
    }
  },
)
