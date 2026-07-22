import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  createServiceAccessRequest,
  getServiceSharingOverview,
  registerSharedService,
  reviewServiceAccessRequest,
  reviewSharedService,
  revokeServiceCredential,
  revokeSharedService,
  runSharedServiceHealthCheck,
} from '@/api/serviceSharing'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  ServiceAccessRequestPayload,
  ServiceRegistrationPayload,
  ServiceSharingOverview,
} from '@/types/serviceSharing'

export const useServiceSharingStore = defineStore('serviceSharing', () => {
  const workbenchStore = useWorkbenchStore()
  const userStore = useUserStore()
  const overviewRef = ref<ServiceSharingOverview | null>(null)
  const loadingRef = ref<boolean>(false)
  const mutatingRef = ref<boolean>(false)
  const oneTimeSecretRef = ref<string | null>(null)
  const canManageComputed = computed<boolean>(() => (
    userStore.hasCapability('manage_services')
  ))
  const canApproveComputed = computed<boolean>(() => (
    userStore.hasCapability('approve_services')
  ))
  const canRequestComputed = computed<boolean>(() => (
    userStore.hasCapability('request_service_access')
  ))
  const canHealthCheckComputed = computed<boolean>(() => (
    userStore.hasCapability('run_service_health_check')
  ))

  const requireUser = () => {
    const user = userStore.currentUserComputed
    if (!user) throw new Error('当前项目用户尚未加载')
    return user
  }

  const load = async (): Promise<void> => {
    const user = requireUser()
    loadingRef.value = true
    try {
      overviewRef.value = await getServiceSharingOverview(
        workbenchStore.projectCodeComputed,
        user.user_code,
      )
    } finally {
      loadingRef.value = false
    }
  }

  const mutate = async (action: () => Promise<unknown>): Promise<void> => {
    mutatingRef.value = true
    try {
      await action()
      await load()
    } finally {
      mutatingRef.value = false
    }
  }

  const register = async (
    payload: Omit<ServiceRegistrationPayload, 'operator_code'>,
  ): Promise<void> => {
    const user = requireUser()
    await mutate(() => registerSharedService(
      workbenchStore.projectCodeComputed,
      { ...payload, operator_code: user.user_code },
    ))
  }

  const reviewService = async (
    serviceCode: string,
    decision: 'approve' | 'reject',
    comment: string,
  ): Promise<void> => {
    const user = requireUser()
    await mutate(() => reviewSharedService(
      workbenchStore.projectCodeComputed,
      serviceCode,
      { decision, comment, operator_code: user.user_code },
    ))
  }

  const requestAccess = async (
    serviceCode: string,
    payload: Omit<ServiceAccessRequestPayload, 'operator_code'>,
  ): Promise<void> => {
    const user = requireUser()
    await mutate(() => createServiceAccessRequest(
      workbenchStore.projectCodeComputed,
      serviceCode,
      { ...payload, operator_code: user.user_code },
    ))
  }

  const reviewAccess = async (
    requestCode: string,
    decision: 'approve' | 'reject',
    comment: string,
  ): Promise<void> => {
    const user = requireUser()
    mutatingRef.value = true
    try {
      const result = await reviewServiceAccessRequest(
        workbenchStore.projectCodeComputed,
        requestCode,
        { decision, comment, operator_code: user.user_code },
      )
      oneTimeSecretRef.value = result.credential_secret
      await load()
    } finally {
      mutatingRef.value = false
    }
  }

  const checkHealth = async (serviceCode: string): Promise<void> => {
    const user = requireUser()
    await mutate(() => runSharedServiceHealthCheck(
      workbenchStore.projectCodeComputed,
      serviceCode,
      user.user_code,
    ))
  }

  const revokeService = async (
    serviceCode: string,
    reason: string,
  ): Promise<void> => {
    const user = requireUser()
    await mutate(() => revokeSharedService(
      workbenchStore.projectCodeComputed,
      serviceCode,
      reason,
      user.user_code,
    ))
  }

  const revokeCredential = async (
    credentialCode: string,
    reason: string,
  ): Promise<void> => {
    const user = requireUser()
    await mutate(() => revokeServiceCredential(
      workbenchStore.projectCodeComputed,
      credentialCode,
      reason,
      user.user_code,
    ))
  }

  const clearOneTimeSecret = (): void => {
    oneTimeSecretRef.value = null
  }

  return {
    overviewRef,
    loadingRef,
    mutatingRef,
    oneTimeSecretRef,
    canManageComputed,
    canApproveComputed,
    canRequestComputed,
    canHealthCheckComputed,
    load,
    register,
    reviewService,
    requestAccess,
    reviewAccess,
    checkHealth,
    revokeService,
    revokeCredential,
    clearOneTimeSecret,
  }
})
