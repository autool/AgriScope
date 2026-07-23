import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

import {
  createUavMobileCapture,
  getUavMobileCaptureOverview,
} from '@/api/uav'
import { useUserStore } from '@/store/userStore'
import type {
  UavMission,
  UavMobileCaptureDraft,
  UavMobileCaptureResult,
} from '@/types/uav'

type UavCaptureStatus =
  | 'idle'
  | 'locating'
  | 'ready'
  | 'submitting'
  | 'completed'
  | 'error'

const DRAFT_STORAGE_KEY = 'agriscope-mobile-uav-capture-v1'

const buildCaptureCode = (): string => {
  const timestamp = new Date().toISOString().replace(/[-:TZ.]/g, '').slice(0, 14)
  const randomValue = globalThis.crypto?.randomUUID
    ? globalThis.crypto.randomUUID().replaceAll('-', '')
    : `${Date.now()}${Math.random().toString(16).slice(2)}`
  return `MOB-${timestamp}-${randomValue.slice(0, 8).toUpperCase()}`
}

const buildDraft = (missionCode: string | null = null): UavMobileCaptureDraft => ({
  capture_code: buildCaptureCode(),
  mission_code: missionCode,
  captured_at: null,
  longitude: null,
  latitude: null,
  location_accuracy_m: null,
  finding_type: null,
  severity: null,
  plot_code: '',
  description: '',
  device_label: '浏览器移动终端',
})

const restoreDraft = (): UavMobileCaptureDraft => {
  try {
    const raw = window.localStorage.getItem(DRAFT_STORAGE_KEY)
    if (!raw) return buildDraft()
    const value: unknown = JSON.parse(raw)
    if (!value || typeof value !== 'object') throw new Error('invalid draft')
    const draft = value as Record<string, unknown>
    if (
      typeof draft.capture_code !== 'string'
      || !/^[-A-Za-z0-9_]+$/.test(draft.capture_code)
      || (draft.mission_code !== null && typeof draft.mission_code !== 'string')
      || (draft.captured_at !== null && typeof draft.captured_at !== 'string')
      || (draft.longitude !== null && typeof draft.longitude !== 'number')
      || (draft.latitude !== null && typeof draft.latitude !== 'number')
      || (
        draft.location_accuracy_m !== null
        && typeof draft.location_accuracy_m !== 'number'
      )
      || (draft.finding_type !== null && typeof draft.finding_type !== 'string')
      || ![null, 'minor', 'major', 'critical'].includes(
        draft.severity as string | null,
      )
      || typeof draft.plot_code !== 'string'
      || typeof draft.description !== 'string'
      || typeof draft.device_label !== 'string'
    ) throw new Error('invalid draft')
    return draft as unknown as UavMobileCaptureDraft
  } catch {
    window.localStorage.removeItem(DRAFT_STORAGE_KEY)
    return buildDraft()
  }
}

export const useUavCaptureStore = defineStore('uav-capture', () => {
  const userStore = useUserStore()
  const projectCodeRef = ref<string>('RS-2026')
  const missionsRef = ref<UavMission[]>([])
  const draftRef = ref<UavMobileCaptureDraft>(restoreDraft())
  const photoFileRef = ref<File | null>(null)
  const resultRef = ref<UavMobileCaptureResult | null>(null)
  const loadingRef = ref<boolean>(false)
  const statusRef = ref<UavCaptureStatus>('idle')
  const errorMessageRef = ref<string>('')
  const onlineRef = ref<boolean>(window.navigator.onLine)
  const secureContextRef = ref<boolean>(window.isSecureContext)

  const selectedMissionComputed = computed<UavMission | null>(() => (
    missionsRef.value.find(
      (mission) => mission.mission_code === draftRef.value.mission_code,
    ) || null
  ))
  const hasLocationComputed = computed<boolean>(() => (
    draftRef.value.longitude !== null
    && draftRef.value.latitude !== null
    && draftRef.value.location_accuracy_m !== null
    && draftRef.value.captured_at !== null
  ))
  const canSubmitComputed = computed<boolean>(() => (
    onlineRef.value
    && userStore.hasCapability('operate_uav_missions')
    && selectedMissionComputed.value !== null
    && hasLocationComputed.value
    && photoFileRef.value !== null
    && Boolean(draftRef.value.finding_type?.trim())
    && draftRef.value.severity !== null
    && draftRef.value.description.trim().length >= 4
    && !['locating', 'submitting'].includes(statusRef.value)
  ))

  watch(
    draftRef,
    (draft) => window.localStorage.setItem(
      DRAFT_STORAGE_KEY,
      JSON.stringify(draft),
    ),
    { deep: true },
  )

  const updateOnlineState = (): void => {
    onlineRef.value = window.navigator.onLine
  }

  const startNetworkMonitoring = (): void => {
    window.addEventListener('online', updateOnlineState)
    window.addEventListener('offline', updateOnlineState)
    updateOnlineState()
  }

  const stopNetworkMonitoring = (): void => {
    window.removeEventListener('online', updateOnlineState)
    window.removeEventListener('offline', updateOnlineState)
  }

  const setProjectCode = (projectCode: string): void => {
    const normalized = projectCode.trim()
    if (normalized) projectCodeRef.value = normalized
  }

  const setPhoto = (photo: File | null): void => {
    photoFileRef.value = photo
    errorMessageRef.value = ''
    if (photo && hasLocationComputed.value) statusRef.value = 'ready'
  }

  const selectMission = (missionCode: string): void => {
    const normalized = missionCode.trim()
    if (!normalized || normalized === draftRef.value.mission_code) return
    draftRef.value = buildDraft(normalized)
    photoFileRef.value = null
    resultRef.value = null
    errorMessageRef.value = ''
    statusRef.value = 'idle'
  }

  const load = async (): Promise<void> => {
    const user = userStore.currentUserComputed
    if (!user || !userStore.hasCapability('operate_uav_missions')) {
      missionsRef.value = []
      throw new Error('请选择具备无人机任务操作权限的项目用户')
    }
    loadingRef.value = true
    errorMessageRef.value = ''
    try {
      const overview = await getUavMobileCaptureOverview(
        projectCodeRef.value,
        user.user_code,
      )
      missionsRef.value = overview.missions
      if (!selectedMissionComputed.value) {
        const firstMissionCode = overview.missions[0]?.mission_code
        if (firstMissionCode) {
          selectMission(firstMissionCode)
        } else {
          draftRef.value.mission_code = null
        }
      }
    } catch (error) {
      missionsRef.value = []
      errorMessageRef.value = error instanceof Error
        ? error.message
        : '无法加载移动采集任务'
      throw error
    } finally {
      loadingRef.value = false
    }
  }

  const captureLocation = async (): Promise<void> => {
    if (!secureContextRef.value) {
      statusRef.value = 'error'
      errorMessageRef.value = '无人机移动采集 GPS 需要通过 HTTPS 安全连接访问'
      throw new Error(errorMessageRef.value)
    }
    if (!('geolocation' in window.navigator)) {
      statusRef.value = 'error'
      errorMessageRef.value = '当前浏览器不支持 GPS 定位'
      throw new Error(errorMessageRef.value)
    }
    statusRef.value = 'locating'
    errorMessageRef.value = ''
    await new Promise<void>((resolve, reject) => {
      window.navigator.geolocation.getCurrentPosition(
        (position) => {
          draftRef.value.longitude = Number(position.coords.longitude.toFixed(8))
          draftRef.value.latitude = Number(position.coords.latitude.toFixed(8))
          draftRef.value.location_accuracy_m = Number(
            position.coords.accuracy.toFixed(2),
          )
          draftRef.value.captured_at = new Date(position.timestamp).toISOString()
          statusRef.value = photoFileRef.value ? 'ready' : 'idle'
          resolve()
        },
        (error) => {
          statusRef.value = 'error'
          errorMessageRef.value = error.message || '无法获取 GPS 位置'
          reject(new Error(errorMessageRef.value))
        },
        {
          enableHighAccuracy: true,
          timeout: 15_000,
          maximumAge: 0,
        },
      )
    })
  }

  const submit = async (): Promise<UavMobileCaptureResult> => {
    const user = userStore.currentUserComputed
    const photo = photoFileRef.value
    const draft = draftRef.value
    if (!user || !userStore.hasCapability('operate_uav_missions')) {
      throw new Error('请选择具备无人机任务操作权限的项目用户')
    }
    if (!canSubmitComputed.value || !photo || !draft.mission_code) {
      throw new Error('请完成任务、GPS、照片和疑点信息后提交')
    }
    if (
      draft.captured_at === null
      || draft.longitude === null
      || draft.latitude === null
      || draft.location_accuracy_m === null
      || draft.finding_type === null
      || draft.severity === null
    ) throw new Error('移动采集信息不完整')
    statusRef.value = 'submitting'
    errorMessageRef.value = ''
    try {
      const result = await createUavMobileCapture(
        projectCodeRef.value,
        draft.mission_code,
        photo,
        {
          capture_code: draft.capture_code,
          captured_at: draft.captured_at,
          longitude: draft.longitude,
          latitude: draft.latitude,
          location_accuracy_m: draft.location_accuracy_m,
          finding_type: draft.finding_type.trim(),
          severity: draft.severity,
          plot_code: draft.plot_code.trim() || undefined,
          description: draft.description.trim(),
          device_label: draft.device_label.trim() || '浏览器移动终端',
          operator_code: user.user_code,
        },
      )
      resultRef.value = result
      statusRef.value = 'completed'
      return result
    } catch (error) {
      statusRef.value = 'error'
      errorMessageRef.value = error instanceof Error
        ? error.message
        : '无人机移动采集提交失败'
      throw error
    }
  }

  const resetDraft = (): void => {
    const missionCode = draftRef.value.mission_code
    draftRef.value = buildDraft(missionCode)
    photoFileRef.value = null
    resultRef.value = null
    errorMessageRef.value = ''
    statusRef.value = 'idle'
  }

  return {
    projectCodeRef,
    missionsRef,
    draftRef,
    photoFileRef,
    resultRef,
    loadingRef,
    statusRef,
    errorMessageRef,
    onlineRef,
    secureContextRef,
    selectedMissionComputed,
    hasLocationComputed,
    canSubmitComputed,
    startNetworkMonitoring,
    stopNetworkMonitoring,
    setProjectCode,
    setPhoto,
    selectMission,
    load,
    captureLocation,
    submit,
    resetDraft,
  }
})
