import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

import { createMobileFieldCapture } from '@/api/fieldCapture'
import { uploadFieldVerificationArtifact } from '@/api/fieldEvidence'
import { useUserStore } from '@/store/userStore'
import type {
  FieldCaptureDraft,
  FieldCaptureResult,
  FieldCaptureStatus,
  PendingFieldPhotoUpload,
} from '@/types/fieldCapture'

const DRAFT_STORAGE_KEY = 'agriscope-mobile-field-draft-v1'
const PENDING_STORAGE_KEY = 'agriscope-mobile-field-pending-v1'

const buildCaptureCode = (): string => {
  const timestamp = new Date().toISOString().replace(/[-:TZ.]/g, '').slice(0, 14)
  const randomValue = globalThis.crypto?.randomUUID
    ? globalThis.crypto.randomUUID().replaceAll('-', '')
    : `${Date.now()}${Math.random().toString(16).slice(2)}`
  const suffix = randomValue.slice(0, 8).toUpperCase()
  return `FV-MOB-${timestamp}-${suffix}`
}

const buildDraft = (): FieldCaptureDraft => {
  const code = buildCaptureCode()
  return {
    verification_code: code,
    source_record_id: code,
    lon: null,
    lat: null,
    location_accuracy_m: null,
    captured_at: null,
    observed_land_class: null,
    observed_crop_type: null,
    remark: '',
  }
}

const isNullableFiniteNumber = (value: unknown): value is number | null => (
  value === null || (typeof value === 'number' && Number.isFinite(value))
)

const isNullableString = (value: unknown): value is string | null => (
  value === null || typeof value === 'string'
)

const isFieldCaptureDraft = (value: unknown): value is FieldCaptureDraft => {
  if (!value || typeof value !== 'object') return false
  const draft = value as Record<string, unknown>
  return typeof draft.verification_code === 'string'
    && draft.verification_code.length > 0
    && typeof draft.source_record_id === 'string'
    && draft.source_record_id.length > 0
    && isNullableFiniteNumber(draft.lon)
    && (draft.lon === null || (draft.lon >= -180 && draft.lon <= 180))
    && isNullableFiniteNumber(draft.lat)
    && (draft.lat === null || (draft.lat >= -90 && draft.lat <= 90))
    && isNullableFiniteNumber(draft.location_accuracy_m)
    && (
      draft.location_accuracy_m === null
      || (draft.location_accuracy_m > 0 && draft.location_accuracy_m <= 10_000)
    )
    && isNullableString(draft.captured_at)
    && isNullableString(draft.observed_land_class)
    && isNullableString(draft.observed_crop_type)
    && typeof draft.remark === 'string'
}

const isPendingFieldPhotoUpload = (
  value: unknown,
): value is PendingFieldPhotoUpload => {
  if (!value || typeof value !== 'object') return false
  const pending = value as Record<string, unknown>
  if (typeof pending.verification_code !== 'string' || !pending.record) {
    return false
  }
  if (typeof pending.record !== 'object') return false
  const record = pending.record as Record<string, unknown>
  return pending.verification_code.length > 0
    && record.verification_code === pending.verification_code
}

const restoreJson = <T>(
  key: string,
  validate: (value: unknown) => value is T,
): T | null => {
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return null
    const value: unknown = JSON.parse(raw)
    if (validate(value)) return value
    window.localStorage.removeItem(key)
    return null
  } catch {
    window.localStorage.removeItem(key)
    return null
  }
}

export const useFieldCaptureStore = defineStore('field-capture', () => {
  const userStore = useUserStore()
  const draftRef = ref<FieldCaptureDraft>(
    restoreJson(DRAFT_STORAGE_KEY, isFieldCaptureDraft) || buildDraft(),
  )
  const taskCodeRef = ref<string>('RS-2026-045')
  const photoFileRef = ref<File | null>(null)
  const pendingUploadRef = ref<PendingFieldPhotoUpload | null>(
    restoreJson(PENDING_STORAGE_KEY, isPendingFieldPhotoUpload),
  )
  const resultRef = ref<FieldCaptureResult | null>(null)
  const statusRef = ref<FieldCaptureStatus>(
    pendingUploadRef.value ? 'pending_photo' : 'idle',
  )
  const errorMessageRef = ref<string>('')
  const onlineRef = ref<boolean>(window.navigator.onLine)
  const secureContextRef = ref<boolean>(window.isSecureContext)

  const hasLocationComputed = computed<boolean>(() => (
    draftRef.value.lon !== null
    && draftRef.value.lat !== null
    && draftRef.value.location_accuracy_m !== null
    && draftRef.value.captured_at !== null
  ))
  const canSubmitComputed = computed<boolean>(() => (
    onlineRef.value
    && hasLocationComputed.value
    && photoFileRef.value !== null
    && Boolean(draftRef.value.observed_land_class)
    && (
      draftRef.value.observed_land_class !== '耕地'
      || Boolean(draftRef.value.observed_crop_type)
    )
    && userStore.hasCapability('upload_field_data')
    && !['creating', 'uploading_photo', 'locating'].includes(statusRef.value)
  ))

  watch(
    draftRef,
    (draft) => window.localStorage.setItem(
      DRAFT_STORAGE_KEY,
      JSON.stringify(draft),
    ),
    { deep: true },
  )
  watch(
    pendingUploadRef,
    (pending) => {
      if (pending) {
        window.localStorage.setItem(PENDING_STORAGE_KEY, JSON.stringify(pending))
      } else {
        window.localStorage.removeItem(PENDING_STORAGE_KEY)
      }
    },
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

  const setTaskCode = (taskCode: string): void => {
    const normalized = taskCode.trim()
    if (normalized) taskCodeRef.value = normalized
  }

  const setPhoto = (file: File | null): void => {
    photoFileRef.value = file
    errorMessageRef.value = ''
  }

  const captureLocation = async (): Promise<void> => {
    if (!secureContextRef.value) {
      statusRef.value = 'error'
      errorMessageRef.value = '移动端 GPS 需要通过 HTTPS 安全连接访问'
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
          draftRef.value.lon = Number(position.coords.longitude.toFixed(8))
          draftRef.value.lat = Number(position.coords.latitude.toFixed(8))
          draftRef.value.location_accuracy_m = Number(
            position.coords.accuracy.toFixed(2),
          )
          draftRef.value.captured_at = new Date(position.timestamp).toISOString()
          statusRef.value = 'ready'
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

  const uploadPendingPhoto = async (): Promise<FieldCaptureResult> => {
    const user = userStore.currentUserComputed
    const pending = pendingUploadRef.value
    const photo = photoFileRef.value
    if (!user || !userStore.hasCapability('upload_field_data')) {
      throw new Error('请选择具备外业采集权限的项目用户')
    }
    if (!pending) throw new Error('没有待补传照片的外业记录')
    if (!photo) throw new Error('请重新选择现场照片')
    if (!onlineRef.value) throw new Error('当前网络离线，无法上传照片')
    statusRef.value = 'uploading_photo'
    try {
      const artifact = await uploadFieldVerificationArtifact(
        pending.verification_code,
        {
          file: photo,
          artifact_type: 'photo',
          uploader_code: user.user_code,
          comment: (
            `移动外业端现场照片；GPS 精度 ${
              pending.record.location_accuracy_m ?? '--'
            } 米`
          ),
        },
      )
      const result: FieldCaptureResult = {
        record: pending.record,
        artifact,
        completed: true,
      }
      resultRef.value = result
      pendingUploadRef.value = null
      photoFileRef.value = null
      statusRef.value = 'completed'
      window.localStorage.removeItem(DRAFT_STORAGE_KEY)
      draftRef.value = buildDraft()
      return result
    } catch (error) {
      statusRef.value = 'pending_photo'
      errorMessageRef.value = error instanceof Error ? error.message : '照片上传失败'
      throw error
    }
  }

  const submitCapture = async (): Promise<FieldCaptureResult> => {
    const user = userStore.currentUserComputed
    const draft = draftRef.value
    if (!user || !userStore.hasCapability('upload_field_data')) {
      throw new Error('请选择具备外业采集权限的项目用户')
    }
    if (!canSubmitComputed.value) throw new Error('请完成定位、现场属性和照片采集')
    statusRef.value = 'creating'
    errorMessageRef.value = ''
    try {
      const record = await createMobileFieldCapture(taskCodeRef.value, {
        verification_code: draft.verification_code,
        source_record_id: draft.source_record_id,
        lon: draft.lon as number,
        lat: draft.lat as number,
        location_accuracy_m: draft.location_accuracy_m as number,
        observed_land_class: draft.observed_land_class,
        observed_crop_type: draft.observed_land_class === '耕地'
          ? draft.observed_crop_type
          : null,
        photo_urls: [],
        voice_url: null,
        remark: draft.remark.trim() || null,
        captured_at: draft.captured_at as string,
        investigator_code: user.user_code,
        source_name: 'AgriScope 移动外业端',
        source_uri: 'app://field-capture/mobile-v1',
        source_version: 'mobile-v1',
      })
      pendingUploadRef.value = {
        verification_code: record.verification_code,
        record,
      }
      statusRef.value = 'pending_photo'
      return await uploadPendingPhoto()
    } catch (error) {
      if (!pendingUploadRef.value) statusRef.value = 'error'
      errorMessageRef.value = error instanceof Error ? error.message : '外业采集提交失败'
      throw error
    }
  }

  const resetDraft = (): void => {
    if (pendingUploadRef.value) return
    draftRef.value = buildDraft()
    photoFileRef.value = null
    resultRef.value = null
    errorMessageRef.value = ''
    statusRef.value = 'idle'
  }

  return {
    draftRef,
    taskCodeRef,
    photoFileRef,
    pendingUploadRef,
    resultRef,
    statusRef,
    errorMessageRef,
    onlineRef,
    secureContextRef,
    hasLocationComputed,
    canSubmitComputed,
    startNetworkMonitoring,
    stopNetworkMonitoring,
    setTaskCode,
    setPhoto,
    captureLocation,
    submitCapture,
    uploadPendingPhoto,
    resetDraft,
  }
})
