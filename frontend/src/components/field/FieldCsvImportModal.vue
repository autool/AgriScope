<script setup lang="ts">
import { DownloadOutlined, InboxOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import type { UploadProps } from 'ant-design-vue'
import { computed, ref, watch } from 'vue'

import type {
  FieldVerificationBatchImportPayload,
  FieldVerificationFileImportMetadata,
  FieldVerificationImportItem,
} from '@/types/workbench'
import { parseCsvRows } from '@/utils/csv'

interface FieldCsvImportModalProps {
  open: boolean
  loading: boolean
}

const props = defineProps<FieldCsvImportModalProps>()
const emit = defineEmits<{
  cancel: []
  submitCsv: [payload: Omit<FieldVerificationBatchImportPayload, 'uploader_code'>]
  submitXlsx: [
    file: File,
    metadata: Omit<FieldVerificationFileImportMetadata, 'uploader_code'>,
  ]
  downloadXlsxTemplate: []
}>()

const requiredHeaders = [
  'verification_code',
  'source_record_id',
  'lon',
  'lat',
  'observed_land_class',
  'observed_crop_type',
  'captured_at',
  'photo_urls',
]
const fileNameRef = ref<string>('')
const selectedFileRef = ref<File | null>(null)
const fileFormatRef = ref<'csv' | 'xlsx' | null>(null)
const sourceNameRef = ref<string>('')
const sourceUriRef = ref<string>('')
const sourceVersionRef = ref<string>('')
const commentRef = ref<string>('')
const recordsRef = ref<FieldVerificationImportItem[]>([])

const canSubmitComputed = computed<boolean>(() => (
  Boolean(selectedFileRef.value)
  && (
    fileFormatRef.value === 'xlsx'
    || (fileFormatRef.value === 'csv' && recordsRef.value.length > 0)
  )
  && Boolean(sourceNameRef.value.trim())
  && Boolean(sourceUriRef.value.trim())
  && Boolean(sourceVersionRef.value.trim())
  && Boolean(commentRef.value.trim())
))

const resetForm = (): void => {
  fileNameRef.value = ''
  selectedFileRef.value = null
  fileFormatRef.value = null
  sourceNameRef.value = ''
  sourceUriRef.value = ''
  sourceVersionRef.value = ''
  commentRef.value = ''
  recordsRef.value = []
}

const parseNumber = (value: string, label: string, rowNumber: number): number => {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    throw new Error(`第 ${rowNumber} 行 ${label} 不是有效数字`)
  }
  return parsed
}

/**
 * 将 CSV 行映射为外业核查导入记录。
 * Args:
 *   text: CSV 文件文本。
 * Returns:
 *   FieldVerificationImportItem[]: 标准化外业记录。
 */
const parseFieldRecords = (text: string): FieldVerificationImportItem[] => {
  const rows = parseCsvRows(text)
  if (rows.length < 2) throw new Error('CSV 必须包含表头和至少一条记录')
  const headers = rows[0].map((value) => value.trim())
  const missingHeader = requiredHeaders.find((header) => !headers.includes(header))
  if (missingHeader) throw new Error(`CSV 缺少必填列 ${missingHeader}`)
  const headerIndex = new Map(headers.map((header, index) => [header, index]))
  const cell = (row: string[], header: string): string => (
    row[headerIndex.get(header) ?? -1]?.trim() || ''
  )
  return rows.slice(1).map((row, index) => {
    const rowNumber = index + 2
    const capturedAt = cell(row, 'captured_at')
    if (!/(Z|[+-]\d{2}:\d{2})$/i.test(capturedAt)) {
      throw new Error(`第 ${rowNumber} 行 captured_at 必须包含时区`)
    }
    const photoUrls = cell(row, 'photo_urls')
      .split('|')
      .map((value) => value.trim())
      .filter(Boolean)
    if (photoUrls.length === 0) {
      throw new Error(`第 ${rowNumber} 行至少需要一个 photo_urls`)
    }
    const landClass = cell(row, 'observed_land_class') || null
    const cropType = cell(row, 'observed_crop_type') || null
    if (landClass === '耕地' && !cropType) {
      throw new Error(`第 ${rowNumber} 行耕地必须填写 observed_crop_type`)
    }
    if (landClass !== '耕地' && cropType) {
      throw new Error(`第 ${rowNumber} 行非耕地不得填写 observed_crop_type`)
    }
    return {
      verification_code: cell(row, 'verification_code'),
      source_record_id: cell(row, 'source_record_id'),
      lon: parseNumber(cell(row, 'lon'), 'lon', rowNumber),
      lat: parseNumber(cell(row, 'lat'), 'lat', rowNumber),
      observed_land_class: landClass,
      observed_crop_type: cropType,
      captured_at: capturedAt,
      photo_urls: photoUrls,
      voice_url: cell(row, 'voice_url') || null,
      remark: cell(row, 'remark') || null,
    }
  })
}

const beforeUpload: UploadProps['beforeUpload'] = async (file) => {
  try {
    if (file.size > 10 * 1024 * 1024) throw new Error('导入文件不得超过 10MB')
    const isCsv = file.name.toLocaleLowerCase().endsWith('.csv')
    const isXlsx = file.name.toLocaleLowerCase().endsWith('.xlsx')
    if (!isCsv && !isXlsx) throw new Error('仅支持 .csv 或 .xlsx 文件')
    if (isCsv) {
      const records = parseFieldRecords(await file.text())
      if (records.length > 500) throw new Error('单次最多导入 500 条外业记录')
      const codes = records.map((item) => item.verification_code)
      if (new Set(codes).size !== codes.length) {
        throw new Error('CSV 内 verification_code 不得重复')
      }
      recordsRef.value = records
      fileFormatRef.value = 'csv'
      message.success(`已读取 ${records.length} 条外业核查记录`)
    } else {
      recordsRef.value = []
      fileFormatRef.value = 'xlsx'
      message.success('已选择 Excel 文件，提交后由服务端校验并原子导入')
    }
    selectedFileRef.value = file
    fileNameRef.value = file.name
    sourceNameRef.value ||= file.name.replace(/\.(csv|xlsx)$/i, '')
  } catch (error) {
    recordsRef.value = []
    fileNameRef.value = ''
    selectedFileRef.value = null
    fileFormatRef.value = null
    message.error(error instanceof Error ? error.message : '导入文件解析失败')
  }
  return false
}

const downloadCsvTemplate = (): void => {
  const header = [
    ...requiredHeaders,
    'voice_url',
    'remark',
  ].join(',')
  const example = [
    'FV-2026-0001',
    'mobile-record-0001',
    '126.450000',
    '45.750000',
    '耕地',
    '玉米',
    '2026-07-22T09:30:00+08:00',
    'https://files.example/field/0001-1.jpg|https://files.example/field/0001-2.jpg',
    'https://files.example/field/0001.m4a',
    '现场边界清晰',
  ].join(',')
  const blob = new Blob([`\uFEFF${header}\r\n${example}\r\n`], {
    type: 'text/csv;charset=utf-8',
  })
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'field_verification_import_template.csv'
  link.click()
  window.URL.revokeObjectURL(url)
}

const handleSubmit = (): void => {
  if (!canSubmitComputed.value || !selectedFileRef.value) return
  const metadata = {
    source_name: sourceNameRef.value.trim(),
    source_uri: sourceUriRef.value.trim(),
    source_version: sourceVersionRef.value.trim(),
    comment: commentRef.value.trim(),
  }
  if (fileFormatRef.value === 'xlsx') {
    emit('submitXlsx', selectedFileRef.value, metadata)
    return
  }
  emit('submitCsv', { ...metadata, records: recordsRef.value })
}

watch(() => props.open, (open) => {
  if (!open) resetForm()
})
</script>

<template>
  <a-modal
    :open="props.open"
    title="批量导入外业核查 CSV / Excel"
    width="680px"
    :confirm-loading="props.loading"
    :ok-button-props="{ disabled: !canSubmitComputed }"
    ok-text="校验、匹配并导入"
    cancel-text="取消"
    @ok="handleSubmit"
    @cancel="emit('cancel')"
  >
    <a-alert
      type="info"
      show-icon
      message="CSV / Excel 将在一个事务中导入并自动匹配"
      description="GPS 必须为 EPSG:4326，采集时间必须含时区，照片使用 | 分隔的受控 URI。Excel 由服务端检查公式、压缩结构和原始文件 SHA256；任一记录不合法时整批回滚。"
    />
    <div class="template-row">
      <span>支持最多 500 条记录</span>
      <div>
        <a-button size="small" @click="downloadCsvTemplate">
          <DownloadOutlined />CSV 模板
        </a-button>
        <a-button size="small" @click="emit('downloadXlsxTemplate')">
          <DownloadOutlined />Excel 模板
        </a-button>
      </div>
    </div>
    <a-upload-dragger
      accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
      :before-upload="beforeUpload"
      :file-list="[]"
      :max-count="1"
    >
      <p class="ant-upload-drag-icon"><InboxOutlined /></p>
      <p class="ant-upload-text">选择或拖入外业核查 CSV / Excel</p>
      <p class="ant-upload-hint">必填列：{{ requiredHeaders.join('、') }}</p>
    </a-upload-dragger>
    <div v-if="fileNameRef" class="file-summary">
      <strong>{{ fileNameRef }}</strong>
      <span v-if="fileFormatRef === 'csv'">{{ recordsRef.length }} 条记录</span>
      <span v-else>Excel · 等待服务端校验</span>
    </div>
    <div class="form-grid">
      <label><span>采集系统/数据源</span><a-input v-model:value="sourceNameRef" placeholder="例如：省级外业采集 App" /></label>
      <label><span>数据版本</span><a-input v-model:value="sourceVersionRef" placeholder="例如：mobile-export-20260722" /></label>
      <label class="full-row"><span>来源 URI</span><a-input v-model:value="sourceUriRef" placeholder="例如：field-app://exports/20260722/batch-01" /></label>
      <label class="full-row"><span>导入依据</span><a-textarea v-model:value="commentRef" :rows="2" placeholder="说明外业批次、调查区域、采集设备或文件交接依据" /></label>
    </div>
  </a-modal>
</template>

<style scoped>
.template-row { display: flex; align-items: center; justify-content: space-between; margin: 10px 0 6px; font-size: 9px; color: #718078; }
.template-row > div { display: flex; gap: 5px; }
.file-summary { display: flex; justify-content: space-between; padding: 8px 10px; margin-top: 8px; font-size: 10px; color: #315b46; background: #f1f7f3; border: 1px solid #dce9e1; border-radius: 5px; }
.file-summary span { color: #718078; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 12px; }
.form-grid label { display: flex; flex-direction: column; gap: 4px; }
.form-grid label > span { font-size: 9px; color: #64736b; }
.form-grid .full-row { grid-column: 1 / -1; }
:deep(.ant-upload-hint) { padding: 0 18px; font-size: 9px; }
</style>
