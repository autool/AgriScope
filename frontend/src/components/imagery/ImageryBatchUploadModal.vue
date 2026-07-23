<script setup lang="ts">
import {
  DeleteOutlined,
  FileImageOutlined,
  InboxOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import type { UploadProps } from 'ant-design-vue'
import type { Dayjs } from 'dayjs'
import { computed, markRaw, ref, watch } from 'vue'

import type {
  ImageryBatchManifest,
  ImageryBatchManifestItem,
} from '@/types/imageryBatch'

interface ImageryBatchUploadModalProps {
  open: boolean
  loading: boolean
  progress: number
  operatorName: string
  operatorRole: string
}

interface ImageryBatchDraftRow {
  rowId: string
  file: File
  assetCode: string
  assetName: string
  sensorType: string
  acquiredAt: Dayjs | null
  cloudCover: number | null
  processingLevel: string
  dataStatus: 'operational' | 'demo'
}

const props = defineProps<ImageryBatchUploadModalProps>()
const emit = defineEmits<{
  cancel: []
  submit: [
    files: File[],
    manifest: Omit<ImageryBatchManifest, 'operator_code'>,
  ]
}>()

const MAX_BATCH_FILES = 20
const SUPPORTED_SUFFIXES = new Set(['.tif', '.tiff', '.img', '.hdf'])

const rowsRef = ref<ImageryBatchDraftRow[]>([])
const batchCodeRef = ref<string>('')
const commentRef = ref<string>('')

const totalSizeComputed = computed<number>(() => (
  rowsRef.value.reduce((total, row) => total + row.file.size, 0)
))

const validationMessagesComputed = computed<string[]>(() => {
  const messages: string[] = []
  const batchCode = batchCodeRef.value.trim()
  if (!/^[A-Za-z0-9_-]{1,90}$/.test(batchCode)) {
    messages.push('批次编号仅允许字母、数字、下划线和连字符')
  }
  if (commentRef.value.trim().length < 10) {
    messages.push('入库依据至少填写 10 个字符')
  }
  if (rowsRef.value.length === 0) {
    messages.push('请选择至少一个影像文件')
  }
  const assetCodes = rowsRef.value.map((row) => row.assetCode.trim())
  if (assetCodes.some((code) => !/^[A-Za-z0-9_-]{1,80}$/.test(code))) {
    messages.push('每个资产编号均须符合编号格式')
  }
  if (new Set(assetCodes).size !== assetCodes.length) {
    messages.push('批次内资产编号不得重复')
  }
  if (rowsRef.value.some((row) => !row.assetName.trim())) {
    messages.push('每个文件均须填写资产名称')
  }
  if (rowsRef.value.some((row) => row.assetName.trim().length > 200)) {
    messages.push('资产名称不得超过 200 个字符')
  }
  if (rowsRef.value.some((row) => row.sensorType.trim().length > 80)) {
    messages.push('传感器补录值不得超过 80 个字符')
  }
  if (rowsRef.value.some((row) => row.processingLevel.trim().length > 30)) {
    messages.push('处理级别补录值不得超过 30 个字符')
  }
  return messages
})

const canSubmitComputed = computed<boolean>(() => (
  !props.loading && validationMessagesComputed.value.length === 0
))

const createBatchCode = (): string => {
  const now = new Date()
  const timestamp = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, '0'),
    String(now.getDate()).padStart(2, '0'),
    String(now.getHours()).padStart(2, '0'),
    String(now.getMinutes()).padStart(2, '0'),
    String(now.getSeconds()).padStart(2, '0'),
  ].join('')
  const random = crypto.randomUUID().replaceAll('-', '').slice(0, 6).toUpperCase()
  return `IMB-${timestamp}-${random}`
}

const baseName = (filename: string): string => (
  filename.replace(/\.[^.]+$/, '')
)

const createAssetCode = (filename: string): string => {
  const normalizedBase = baseName(filename)
    .replace(/[^A-Za-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .toUpperCase()
    .slice(0, 72) || 'IMAGERY'
  const usedCodes = new Set(rowsRef.value.map((row) => row.assetCode.trim()))
  if (!usedCodes.has(normalizedBase)) return normalizedBase
  for (let index = 2; index <= MAX_BATCH_FILES + 1; index += 1) {
    const suffix = `-${index}`
    const candidate = `${normalizedBase.slice(0, 80 - suffix.length)}${suffix}`
    if (!usedCodes.has(candidate)) return candidate
  }
  return `${normalizedBase.slice(0, 73)}-${crypto.randomUUID().slice(0, 6)}`
}

const formatBytes = (size: number): string => {
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  if (size < 1024 * 1024 * 1024) {
    return `${(size / 1024 / 1024).toFixed(1)} MB`
  }
  return `${(size / 1024 / 1024 / 1024).toFixed(2)} GB`
}

const fileSuffix = (filename: string): string => {
  const matched = filename.toLowerCase().match(/\.[^.]+$/)
  return matched?.[0] || ''
}

const beforeUpload: UploadProps['beforeUpload'] = (file) => {
  if (props.loading) return false
  if (rowsRef.value.length >= MAX_BATCH_FILES) {
    message.warning(`单批最多选择 ${MAX_BATCH_FILES} 个文件`)
    return false
  }
  if (!SUPPORTED_SUFFIXES.has(fileSuffix(file.name))) {
    message.error(`文件 ${file.name} 不是支持的 GeoTIFF、IMG 或 HDF`)
    return false
  }
  if (file.size === 0) {
    message.error(`文件 ${file.name} 为空`)
    return false
  }
  if (rowsRef.value.some(
    (row) => row.file.name.toLowerCase() === file.name.toLowerCase(),
  )) {
    message.warning(`文件名 ${file.name} 已在当前批次中`)
    return false
  }
  rowsRef.value.push({
    rowId: crypto.randomUUID(),
    file: markRaw(file),
    assetCode: createAssetCode(file.name),
    assetName: baseName(file.name),
    sensorType: '',
    acquiredAt: null,
    cloudCover: null,
    processingLevel: '',
    dataStatus: 'operational',
  })
  return false
}

const removeRow = (rowId: string): void => {
  if (props.loading) return
  rowsRef.value = rowsRef.value.filter((row) => row.rowId !== rowId)
}

const resetForm = (): void => {
  rowsRef.value = []
  batchCodeRef.value = createBatchCode()
  commentRef.value = ''
}

const handleCancel = (): void => {
  if (props.loading) return
  emit('cancel')
}

const handleSubmit = (): void => {
  if (!canSubmitComputed.value) {
    message.warning(validationMessagesComputed.value[0] || '请完善批次清单')
    return
  }
  const items: ImageryBatchManifestItem[] = rowsRef.value.map((row) => ({
    filename: row.file.name,
    asset_code: row.assetCode.trim(),
    asset_name: row.assetName.trim(),
    sensor_type: row.sensorType.trim() || null,
    acquired_at: row.acquiredAt?.toISOString() || null,
    cloud_cover: row.cloudCover,
    processing_level: row.processingLevel.trim() || null,
    data_status: row.dataStatus,
  }))
  emit(
    'submit',
    rowsRef.value.map((row) => row.file),
    {
      batch_code: batchCodeRef.value.trim(),
      comment: commentRef.value.trim(),
      items,
    },
  )
}

watch(
  () => props.open,
  (open) => {
    if (open) resetForm()
  },
  { immediate: true },
)
</script>

<template>
  <a-modal
    class="imagery-batch-modal"
    :open="props.open"
    title="遥感影像原子批量入库"
    width="1120px"
    :confirm-loading="props.loading"
    :mask-closable="!props.loading"
    :keyboard="!props.loading"
    :closable="!props.loading"
    :ok-button-props="{ disabled: !canSubmitComputed }"
    :cancel-button-props="{ disabled: props.loading }"
    ok-text="原子校验并入库"
    cancel-text="取消"
    @ok="handleSubmit"
    @cancel="handleCancel"
  >
    <a-alert
      type="info"
      show-icon
      message="整批成功或整批回滚"
      description="支持一次导入 1–20 个 GeoTIFF、IMG 或 HDF。服务端会逐文件读取实体元数据、校验文件名/资产编号/SHA256 去重；任一文件失败时，不保留数据库记录和已发布文件。"
    />

    <section class="batch-overview">
      <a-upload-dragger
        accept=".tif,.tiff,.img,.hdf"
        multiple
        :before-upload="beforeUpload"
        :file-list="[]"
        :disabled="props.loading || rowsRef.length >= MAX_BATCH_FILES"
      >
        <p class="ant-upload-drag-icon"><InboxOutlined /></p>
        <p class="ant-upload-text">选择或拖入多景遥感影像</p>
        <p class="ant-upload-hint">
          已选择 {{ rowsRef.length }}/{{ MAX_BATCH_FILES }} 个文件，合计 {{ formatBytes(totalSizeComputed) }}
        </p>
      </a-upload-dragger>

      <div class="batch-fields">
        <label>
          <span>批次编号</span>
          <a-input
            v-model:value="batchCodeRef"
            :disabled="props.loading"
            placeholder="字母、数字、下划线或连字符"
          />
        </label>
        <label>
          <span>稳定操作身份</span>
          <strong>{{ props.operatorName || '--' }} · {{ props.operatorRole || '--' }}</strong>
        </label>
        <label class="comment-field">
          <span>入库依据</span>
          <a-textarea
            v-model:value="commentRef"
            :disabled="props.loading"
            :rows="2"
            :maxlength="500"
            show-count
            placeholder="至少 10 个字符，说明数据交接批次、公开来源或生产任务依据"
          />
        </label>
      </div>
    </section>

    <a-empty
      v-if="rowsRef.length === 0"
      class="batch-empty"
      description="尚未选择影像文件"
    />

    <section v-else class="manifest-list">
      <article v-for="(row, index) in rowsRef" :key="row.rowId">
        <header>
          <span class="file-index">{{ index + 1 }}</span>
          <FileImageOutlined />
          <span class="file-identity">
            <strong>{{ row.file.name }}</strong>
            <small>{{ formatBytes(row.file.size) }} · 服务端将读取驱动、CRS、范围、分辨率、尺寸、波段和标签</small>
          </span>
          <a-tag :color="row.dataStatus === 'operational' ? 'green' : 'orange'">
            {{ row.dataStatus === 'operational' ? '业务数据' : '明确演示' }}
          </a-tag>
          <a-button
            type="text"
            danger
            :disabled="props.loading"
            title="移出当前批次"
            @click="removeRow(row.rowId)"
          >
            <DeleteOutlined />
          </a-button>
        </header>

        <div class="item-grid">
          <label>
            <span>资产编号</span>
            <a-input
              v-model:value="row.assetCode"
              :disabled="props.loading"
              :maxlength="80"
            />
          </label>
          <label>
            <span>资产名称</span>
            <a-input
              v-model:value="row.assetName"
              :disabled="props.loading"
              :maxlength="200"
            />
          </label>
          <label>
            <span>传感器补录</span>
            <a-input
              v-model:value="row.sensorType"
              :disabled="props.loading"
              :maxlength="80"
              placeholder="文件标签缺失时填写"
            />
          </label>
          <label>
            <span>采集时间补录</span>
            <a-date-picker
              v-model:value="row.acquiredAt"
              show-time
              :disabled="props.loading"
              placeholder="缺失或仅有日期时填写"
            />
          </label>
          <label>
            <span>云量补录</span>
            <a-input-number
              v-model:value="row.cloudCover"
              :disabled="props.loading"
              :min="0"
              :max="100"
              addon-after="%"
              placeholder="文件标签缺失时填写"
            />
          </label>
          <label>
            <span>处理级别补录</span>
            <a-input
              v-model:value="row.processingLevel"
              :disabled="props.loading"
              :maxlength="30"
              placeholder="文件标签缺失时填写"
            />
          </label>
          <label>
            <span>数据属性</span>
            <a-select v-model:value="row.dataStatus" :disabled="props.loading">
              <a-select-option value="operational">业务数据</a-select-option>
              <a-select-option value="demo">明确演示数据</a-select-option>
            </a-select>
          </label>
          <p>文件标签优先；人工值仅作缺失补录或日期精度补充，冲突时整批拒绝。</p>
        </div>
      </article>
    </section>

    <a-alert
      v-if="validationMessagesComputed.length && rowsRef.length"
      class="validation-alert"
      type="warning"
      show-icon
      :message="validationMessagesComputed[0]"
      :description="validationMessagesComputed.slice(1).join('；') || undefined"
    />
    <a-progress
      v-if="props.loading"
      class="upload-progress"
      :percent="props.progress"
      status="active"
    />
  </a-modal>
</template>

<style scoped>
.batch-overview { display: grid; grid-template-columns: 330px minmax(0, 1fr); gap: 12px; margin-top: 12px; }
.batch-overview :deep(.ant-upload-drag) { min-height: 150px; }
.batch-overview :deep(.ant-upload-hint) { padding: 0 18px; font-size: 9px; }
.batch-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; padding: 12px; background: #f7f9f8; border: 1px solid #e1e7e3; border-radius: 6px; }
.batch-fields label, .item-grid label { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.batch-fields label > span, .item-grid label > span { font-size: 9px; color: #68766f; }
.batch-fields label > strong { padding: 5px 0; font-size: 10px; color: #315b46; }
.batch-fields .comment-field { grid-column: 1 / -1; }
.batch-empty { padding: 30px 0 16px; }
.manifest-list { max-height: 440px; padding-right: 4px; margin-top: 12px; overflow: auto; }
.manifest-list article { margin-bottom: 8px; border: 1px solid #dfe6e2; border-radius: 6px; }
.manifest-list article > header { display: grid; grid-template-columns: 24px 20px minmax(0, 1fr) auto 32px; gap: 8px; align-items: center; padding: 8px 10px; background: #f4f7f5; border-bottom: 1px solid #e2e8e4; }
.file-index { display: grid; width: 20px; height: 20px; font-size: 9px; color: #fff; place-items: center; background: #3d7f5c; border-radius: 50%; }
.file-identity { display: flex; flex-direction: column; min-width: 0; }
.file-identity strong { overflow: hidden; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.file-identity small { overflow: hidden; font-size: 8px; color: #7d8983; text-overflow: ellipsis; white-space: nowrap; }
.item-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; padding: 10px; }
.item-grid :deep(.ant-picker), .item-grid :deep(.ant-input-number) { width: 100%; }
.item-grid p { align-self: end; margin: 0; font-size: 8px; line-height: 1.5; color: #78847e; }
.validation-alert, .upload-progress { margin-top: 10px; }
@media (max-width: 1000px) {
  .batch-overview { grid-template-columns: 1fr; }
  .item-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
