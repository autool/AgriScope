<script setup lang="ts">
import { DownloadOutlined, FileProtectOutlined, UploadOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, ref, watch } from 'vue'

import { useFieldStore } from '@/store/fieldStore'
import type {
  FieldVerificationArtifact,
  FieldVerificationArtifactType,
} from '@/types/workbench'

const fieldStore = useFieldStore()
const {
  canUploadComputed,
  canViewEvidenceComputed,
  downloadingArtifactCodeRef,
  selectedRecordComputed,
  uploadingArtifactRef,
} = storeToRefs(fieldStore)

const artifactTypeRef = ref<FieldVerificationArtifactType>('photo')
const selectedFileRef = ref<File | null>(null)
const commentRef = ref<string>('')

const acceptComputed = computed<string>(() => ({
  photo: '.jpg,.jpeg,.png,.webp',
  voice: '.wav,.mp3,.m4a,.ogg',
  form: '.pdf,.xlsx',
})[artifactTypeRef.value])

const verifiedPhotoCountComputed = computed<number>(() => (
  selectedRecordComputed.value?.artifacts.filter(
    (item) => item.artifact_type === 'photo',
  ).length || 0
))

const legacyReferenceCountComputed = computed<number>(() => (
  (selectedRecordComputed.value?.photo_urls.length || 0)
  + (selectedRecordComputed.value?.voice_url ? 1 : 0)
))

const artifactTypeLabel = (value: FieldVerificationArtifactType): string => ({
  photo: '现场照片',
  voice: '语音备注',
  form: '调查表',
})[value]

const formatBytes = (value: number): string => {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

/**
 * 接收浏览器选择的单个证据文件。
 * Args:
 *   event: 文件输入变化事件。
 * Returns:
 *   void: 更新本地待上传文件。
 */
const handleFileChange = (event: Event): void => {
  const input = event.target as HTMLInputElement
  selectedFileRef.value = input.files?.[0] || null
}

/**
 * 上传当前记录的受控实体证据。
 * Returns:
 *   Promise<void>: 服务端校验、持久化和列表刷新完成后结束。
 */
const handleUpload = async (): Promise<void> => {
  if (!selectedFileRef.value) {
    message.warning('请选择需要上传的实体文件')
    return
  }
  const comment = commentRef.value.trim()
  if (comment.length < 2) {
    message.warning('请填写证据来源、采集设备或调查用途说明')
    return
  }
  try {
    const artifact = await fieldStore.uploadArtifact(
      selectedFileRef.value,
      artifactTypeRef.value,
      comment,
    )
    selectedFileRef.value = null
    commentRef.value = ''
    message.success(`实体证据 ${artifact.artifact_code} 已通过完整性校验`)
  } catch {
    // 请求拦截器已显示服务端安全错误。
  }
}

/**
 * 下载一份已验证实体证据。
 * Args:
 *   artifact: 实体证据摘要。
 * Returns:
 *   Promise<void>: 浏览器下载动作触发后结束。
 */
const handleDownload = async (
  artifact: FieldVerificationArtifact,
): Promise<void> => {
  try {
    const { blob, filename } = await fieldStore.downloadArtifact(artifact)
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    window.URL.revokeObjectURL(url)
  } catch {
    // 请求拦截器已显示服务端安全错误。
  }
}

watch(
  () => selectedRecordComputed.value?.verification_code,
  () => {
    selectedFileRef.value = null
    commentRef.value = ''
  },
)
</script>

<template>
  <section v-if="selectedRecordComputed" class="evidence-panel">
    <header>
      <span><FileProtectOutlined /> 实体证据</span>
      <a-tag :color="verifiedPhotoCountComputed > 0 ? 'success' : 'error'">
        已验证照片 {{ verifiedPhotoCountComputed }} 张
      </a-tag>
    </header>

    <a-alert
      v-if="verifiedPhotoCountComputed === 0"
      type="warning"
      show-icon
      message="缺少可复核的现场照片实体"
      description="历史 URL 不能作为交付证据；疑点闭环和成果包生成前必须上传至少一张通过格式、大小和 SHA-256 校验的现场照片。"
    />

    <div v-if="selectedRecordComputed.artifacts.length" class="artifact-list">
      <article
        v-for="artifact in selectedRecordComputed.artifacts"
        :key="artifact.artifact_code"
      >
        <div class="artifact-main">
          <span class="artifact-type">{{ artifactTypeLabel(artifact.artifact_type) }}</span>
          <strong :title="artifact.original_filename">{{ artifact.original_filename }}</strong>
          <small>{{ formatBytes(artifact.file_size_bytes) }} · {{ artifact.media_type }}</small>
          <small :title="artifact.checksum_sha256">SHA {{ artifact.checksum_sha256.slice(0, 16) }}…</small>
          <small>{{ artifact.uploaded_by }} · {{ artifact.description }}</small>
        </div>
        <a-button
          size="small"
          :disabled="!canViewEvidenceComputed"
          :loading="downloadingArtifactCodeRef === artifact.artifact_code"
          @click="handleDownload(artifact)"
        >
          <DownloadOutlined /> 下载
        </a-button>
      </article>
    </div>
    <a-empty
      v-else
      :image-style="{ height: '34px' }"
      description="尚未上传受控实体证据"
    />

    <div v-if="canUploadComputed" class="upload-form">
      <a-select v-model:value="artifactTypeRef" size="small">
        <a-select-option value="photo">现场照片</a-select-option>
        <a-select-option value="voice">语音备注</a-select-option>
        <a-select-option value="form">调查表</a-select-option>
      </a-select>
      <label class="file-picker">
        <input :accept="acceptComputed" type="file" @change="handleFileChange">
        <span><UploadOutlined /> {{ selectedFileRef?.name || '选择实体文件' }}</span>
      </label>
      <a-textarea
        v-model:value="commentRef"
        :rows="2"
        :maxlength="500"
        placeholder="说明采集设备、调查批次、拍摄方向或表单来源"
      />
      <a-button
        type="primary"
        size="small"
        :loading="uploadingArtifactRef"
        :disabled="!selectedFileRef || commentRef.trim().length < 2"
        @click="handleUpload"
      >
        上传并校验
      </a-button>
      <small class="format-help">
        照片 JPG/PNG/WebP ≤20MB；语音 WAV/MP3/M4A/OGG ≤100MB；调查表 PDF/XLSX ≤50MB。
      </small>
    </div>

    <a-collapse v-if="legacyReferenceCountComputed > 0" ghost>
      <a-collapse-panel key="legacy" header="历史外部引用（未经实体校验）">
        <ul class="legacy-list">
          <li v-for="url in selectedRecordComputed.photo_urls" :key="url" :title="url">
            照片外链：{{ url }}
          </li>
          <li v-if="selectedRecordComputed.voice_url" :title="selectedRecordComputed.voice_url">
            语音外链：{{ selectedRecordComputed.voice_url }}
          </li>
        </ul>
      </a-collapse-panel>
    </a-collapse>
  </section>
</template>

<style scoped>
.evidence-panel { display: grid; gap: 8px; padding: 9px; margin-top: 10px; background: #f8faf9; border: 1px solid #e2e8e5; border-radius: 6px; }
.evidence-panel header { display: flex; align-items: center; justify-content: space-between; font-size: 9px; font-weight: 700; }
.artifact-list { display: grid; gap: 5px; }
.artifact-list article { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; align-items: center; padding: 7px; background: #fff; border: 1px solid #e4e9e6; border-radius: 5px; }
.artifact-main { display: grid; min-width: 0; }
.artifact-main strong { overflow: hidden; font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }
.artifact-main small { overflow: hidden; font-size: 7px; color: #76827c; text-overflow: ellipsis; white-space: nowrap; }
.artifact-type { width: max-content; padding: 1px 5px; margin-bottom: 3px; font-size: 7px; color: #276a4a; background: #eaf4ef; border-radius: 999px; }
.upload-form { display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: 6px; padding-top: 8px; border-top: 1px dashed #dce3df; }
.upload-form :deep(.ant-input) { grid-column: 1 / -1; font-size: 8px; }
.upload-form > .ant-btn { grid-column: 1 / -1; }
.format-help { grid-column: 1 / -1; font-size: 7px; line-height: 1.5; color: #7e8983; }
.file-picker { position: relative; min-width: 0; padding: 3px 8px; overflow: hidden; font-size: 8px; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; background: #fff; border: 1px solid #d8dfdb; border-radius: 4px; }
.file-picker input { position: absolute; width: 1px; height: 1px; opacity: 0; }
.legacy-list { padding-left: 16px; margin: 0; }
.legacy-list li { overflow: hidden; font-size: 7px; color: #8a7460; text-overflow: ellipsis; white-space: nowrap; }
</style>
