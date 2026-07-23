import type {
  FieldVerificationArtifact,
  FieldVerificationItem,
} from '@/types/workbench'

export interface FieldCaptureDraft {
  verification_code: string
  source_record_id: string
  lon: number | null
  lat: number | null
  location_accuracy_m: number | null
  captured_at: string | null
  observed_land_class: string | null
  observed_crop_type: string | null
  remark: string
}

export interface FieldCaptureCreatePayload {
  verification_code: string
  source_record_id: string
  lon: number
  lat: number
  location_accuracy_m: number
  observed_land_class: string | null
  observed_crop_type: string | null
  photo_urls: string[]
  voice_url: string | null
  remark: string | null
  captured_at: string
  investigator_code: string
  source_name: string
  source_uri: string
  source_version: string
}

export interface PendingFieldPhotoUpload {
  verification_code: string
  record: FieldVerificationItem
}

export interface FieldCaptureResult {
  record: FieldVerificationItem
  artifact: FieldVerificationArtifact | null
  completed: boolean
}

export type FieldCaptureStatus =
  | 'idle'
  | 'locating'
  | 'ready'
  | 'creating'
  | 'uploading_photo'
  | 'pending_photo'
  | 'completed'
  | 'error'
