import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  createUavFinding,
  createUavMission,
  downloadUavArtifact,
  getUavOverview,
  registerUavAircraft,
  reviewUavFinding,
  transitionUavMission,
  uploadUavArtifact,
} from '@/api/uav'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  AircraftUploadMetadata,
  ArtifactUploadMetadata,
  MissionUploadMetadata,
  UavFindingCreatePayload,
  UavMissionAction,
  UavOverview,
} from '@/types/uav'

export const useUavStore = defineStore('uav', () => {
  const userStore = useUserStore()
  const workbenchStore = useWorkbenchStore()
  const overviewRef = ref<UavOverview | null>(null)
  const loadingRef = ref<boolean>(false)
  const mutatingRef = ref<boolean>(false)

  const canManageAircraftComputed = computed(() => (
    userStore.hasCapability('manage_uav_aircraft')
  ))
  const canManageMissionsComputed = computed(() => (
    userStore.hasCapability('manage_uav_missions')
  ))
  const canOperateComputed = computed(() => (
    userStore.hasCapability('operate_uav_missions')
  ))
  const canReviewComputed = computed(() => (
    userStore.hasCapability('review_uav_findings')
  ))
  const canDownloadComputed = computed(() => (
    userStore.hasCapability('download_uav_artifacts')
  ))

  const requireUserCode = (): string => {
    const userCode = userStore.currentUserComputed?.user_code
    if (!userCode) throw new Error('当前项目用户尚未加载')
    return userCode
  }

  const load = async (): Promise<void> => {
    const userCode = requireUserCode()
    loadingRef.value = true
    try {
      overviewRef.value = await getUavOverview(
        workbenchStore.projectCodeComputed,
        userCode,
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

  const registerAircraft = async (
    file: File,
    metadata: AircraftUploadMetadata,
  ): Promise<void> => mutate(() => registerUavAircraft(
    workbenchStore.projectCodeComputed,
    file,
    metadata,
    requireUserCode(),
  ))

  const createMission = async (
    file: File,
    metadata: MissionUploadMetadata,
  ): Promise<void> => mutate(() => createUavMission(
    workbenchStore.projectCodeComputed,
    workbenchStore.taskCodeComputed,
    file,
    metadata,
    requireUserCode(),
  ))

  const uploadArtifact = async (
    missionCode: string,
    file: File,
    metadata: ArtifactUploadMetadata,
  ): Promise<void> => mutate(() => uploadUavArtifact(
    workbenchStore.projectCodeComputed,
    missionCode,
    file,
    metadata,
    requireUserCode(),
  ))

  const transition = async (
    missionCode: string,
    action: UavMissionAction,
    comment: string,
    actualTime: string | null,
  ): Promise<void> => mutate(() => transitionUavMission(
    workbenchStore.projectCodeComputed,
    missionCode,
    action,
    comment,
    actualTime,
    requireUserCode(),
  ))

  const createFinding = async (
    missionCode: string,
    payload: Omit<UavFindingCreatePayload, 'operator_code'>,
  ): Promise<void> => mutate(() => createUavFinding(
    workbenchStore.projectCodeComputed,
    missionCode,
    { ...payload, operator_code: requireUserCode() },
  ))

  const reviewFinding = async (
    missionCode: string,
    findingCode: string,
    decision: 'confirm' | 'dismiss',
    comment: string,
  ): Promise<void> => mutate(() => reviewUavFinding(
    workbenchStore.projectCodeComputed,
    missionCode,
    findingCode,
    decision,
    comment,
    requireUserCode(),
  ))

  const downloadArtifact = async (
    artifactCode: string,
    filename: string,
  ): Promise<void> => {
    const blob = await downloadUavArtifact(
      workbenchStore.projectCodeComputed,
      artifactCode,
      requireUserCode(),
    )
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
  }

  return {
    overviewRef,
    loadingRef,
    mutatingRef,
    canManageAircraftComputed,
    canManageMissionsComputed,
    canOperateComputed,
    canReviewComputed,
    canDownloadComputed,
    load,
    registerAircraft,
    createMission,
    uploadArtifact,
    transition,
    createFinding,
    reviewFinding,
    downloadArtifact,
  }
})
