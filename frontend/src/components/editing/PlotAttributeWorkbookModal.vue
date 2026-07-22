<script setup lang="ts">
import { FileExcelOutlined, UploadOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, ref, watch } from 'vue'

import { usePlotAttributeWorkbookStore } from '@/store/plotAttributeWorkbookStore'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'

interface PlotAttributeWorkbookModalProps {
  open: boolean
}

const props = defineProps<PlotAttributeWorkbookModalProps>()
const emit = defineEmits<{ cancel: [] }>()
const workbookStore = usePlotAttributeWorkbookStore()
const workbenchStore = useWorkbenchStore()
const userStore = useUserStore()
const {
  historyRef,
  latestResultRef,
  loadingHistoryRef,
  exportingRef,
  importingRef,
  canExportComputed,
  canImportComputed,
} = storeToRefs(workbookStore)

const scopeRef = ref<'current' | 'explicit' | 'task'>('current')
const explicitCodesRef = ref<string>('')
const selectedFileRef = ref<File | null>(null)
const selectedFilenameRef = ref<string>('')
const commentRef = ref<string>('')

const currentPlotCodeComputed = computed<string | null>(
  () => workbenchStore.selectedPlotCodeComputed,
)

const parsedCodesComputed = computed<string[]>(() => {
  const seen = new Set<string>()
  return explicitCodesRef.value
    .split(/[\s,，;；]+/)
    .map((item) => item.trim())
    .filter((item) => {
      if (!item || seen.has(item)) return false
      seen.add(item)
      return true
    })
})

const exportCodesComputed = computed<string[] | undefined>(() => {
  if (scopeRef.value === 'task') return undefined
  if (scopeRef.value === 'current') {
    return currentPlotCodeComputed.value
      ? [currentPlotCodeComputed.value]
      : []
  }
  return parsedCodesComputed.value
})

const exportDisabledComputed = computed<boolean>(() => (
  !canExportComputed.value
  || exportingRef.value
  || (scopeRef.value !== 'task' && !exportCodesComputed.value?.length)
  || parsedCodesComputed.value.length > 500
))

const importDisabledComputed = computed<boolean>(() => (
  !canImportComputed.value
  || importingRef.value
  || !selectedFileRef.value
  || commentRef.value.trim().length < 2
))

const formatBytes = (value: number): string => {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(2)} MB`
}

const formatTime = (value: string): string => new Date(value).toLocaleString('zh-CN')

const shortHash = (value: string): string => `${value.slice(0, 12)}…${value.slice(-8)}`

const downloadBlob = (blob: Blob, filename: string): void => {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  window.URL.revokeObjectURL(url)
}

const handleExport = async (): Promise<void> => {
  if (parsedCodesComputed.value.length > 500) {
    message.warning('显式范围单次最多填写 500 个图斑编号')
    return
  }
  try {
    const result = await workbookStore.exportWorkbook(exportCodesComputed.value)
    downloadBlob(result.blob, result.filename)
    const count = exportCodesComputed.value?.length
    message.success(count ? `已导出 ${count} 个图斑属性` : '任务属性工作簿已导出')
  } catch (error) {
    if (error instanceof Error && error.message.includes('无权')) {
      message.warning(error.message)
    }
  }
}

const beforeUpload = (file: File): boolean => {
  if (!file.name.toLowerCase().endsWith('.xlsx')) {
    message.warning('仅支持 .xlsx 地块属性工作簿')
    return false
  }
  if (file.size > 10 * 1024 * 1024) {
    message.warning('Excel 文件不得超过 10MB')
    return false
  }
  selectedFileRef.value = file
  selectedFilenameRef.value = file.name
  return false
}

const clearFile = (): void => {
  selectedFileRef.value = null
  selectedFilenameRef.value = ''
}

const handleImport = async (): Promise<void> => {
  const file = selectedFileRef.value
  if (!file || importDisabledComputed.value) return
  try {
    const result = await workbookStore.importWorkbook(
      file,
      commentRef.value.trim(),
    )
    message.success(
      `原子导入完成：更新 ${result.changed_count} 个，未变化 ${result.unchanged_count} 个`,
    )
    clearFile()
    commentRef.value = ''
  } catch (error) {
    if (error instanceof Error && error.message.includes('无权')) {
      message.warning(error.message)
    }
  }
}

watch(
  () => props.open,
  (open) => {
    if (!open) return
    scopeRef.value = currentPlotCodeComputed.value ? 'current' : 'explicit'
    explicitCodesRef.value = currentPlotCodeComputed.value || ''
    clearFile()
    commentRef.value = ''
    workbookStore.loadHistory().catch(() => undefined)
  },
)
</script>

<template>
  <a-modal
    :open="props.open"
    title="地块属性 Excel 逐行维护"
    width="920px"
    :footer="null"
    :mask-closable="false"
    @cancel="emit('cancel')"
  >
    <a-alert
      type="warning"
      show-icon
      message="整批原子校验与写入"
      description="服务端会检查任务范围、重复编号、地类作物逻辑和 expected_version。任意一行失败时，全部图斑均不写入；成功后每个实际变化图斑生成独立版本并要求重新质检。"
    />

    <div class="workflow-grid">
      <section class="workflow-card export-card">
        <header>
          <span class="step-index">1</span>
          <div>
            <strong>导出当前属性</strong>
            <small>生成带版本锁的服务端 XLSX</small>
          </div>
        </header>

        <a-radio-group v-model:value="scopeRef" class="scope-options">
          <a-radio value="current" :disabled="!currentPlotCodeComputed">
            当前图斑
            <small>{{ currentPlotCodeComputed || '尚未选择图斑' }}</small>
          </a-radio>
          <a-radio value="explicit">
            显式编号范围
            <small>支持换行、逗号或分号分隔</small>
          </a-radio>
          <a-radio value="task">
            当前任务全部
            <small>仅适用于有效图斑不超过 500 个的任务</small>
          </a-radio>
        </a-radio-group>

        <a-textarea
          v-if="scopeRef === 'explicit'"
          v-model:value="explicitCodesRef"
          :rows="5"
          placeholder="例如：HLJ-230109-0001, HLJ-230109-0002"
        />
        <div v-if="scopeRef === 'explicit'" class="range-count" :class="{ invalid: parsedCodesComputed.length > 500 }">
          已识别 {{ parsedCodesComputed.length }} / 500 个唯一编号
        </div>

        <a-button
          type="primary"
          block
          :loading="exportingRef"
          :disabled="exportDisabledComputed"
          @click="handleExport"
        >
          <FileExcelOutlined />导出可回写工作簿
        </a-button>
      </section>

      <section class="workflow-card import-card">
        <header>
          <span class="step-index">2</span>
          <div>
            <strong>上传并原子回写</strong>
            <small>原始文件、大小和 SHA-256 受控留存</small>
          </div>
        </header>

        <a-upload-dragger
          accept=".xlsx"
          :max-count="1"
          :show-upload-list="false"
          :before-upload="beforeUpload"
          :disabled="!canImportComputed"
        >
          <p class="ant-upload-drag-icon"><UploadOutlined /></p>
          <p class="ant-upload-text">
            {{ selectedFilenameRef || '选择编辑完成的 .xlsx 工作簿' }}
          </p>
          <p class="ant-upload-hint">最大 10MB；公式、加密包和非标准表头会被拒绝</p>
        </a-upload-dragger>

        <label class="comment-field">
          <span>判读与修改依据 <b>*</b></span>
          <a-textarea
            v-model:value="commentRef"
            :rows="4"
            placeholder="说明采用的卫星影像时相、外业调查记录或属性确认依据"
          />
        </label>

        <div class="operator-row">
          <span>操作身份</span>
          <strong>
            {{ userStore.currentUserComputed?.display_name || '--' }} ·
            {{ userStore.currentUserComputed?.role_name || '--' }}
          </strong>
        </div>

        <a-button
          danger
          type="primary"
          block
          :loading="importingRef"
          :disabled="importDisabledComputed"
          @click="handleImport"
        >
          校验全部行并原子导入
        </a-button>
      </section>
    </div>

    <section v-if="latestResultRef" class="result-card">
      <header>
        <strong>最近一次导入结果</strong>
        <a-tag :color="latestResultRef.changed_count ? 'processing' : 'default'">
          {{ latestResultRef.quality_recheck_required ? '需要重新质检' : '数据未变化' }}
        </a-tag>
      </header>
      <dl>
        <div><dt>批次</dt><dd>{{ latestResultRef.batch_code }}</dd></div>
        <div><dt>行数</dt><dd>{{ latestResultRef.row_count }}</dd></div>
        <div><dt>已更新</dt><dd>{{ latestResultRef.changed_count }}</dd></div>
        <div><dt>未变化</dt><dd>{{ latestResultRef.unchanged_count }}</dd></div>
        <div><dt>文件大小</dt><dd>{{ formatBytes(latestResultRef.file_size_bytes) }}</dd></div>
        <div class="hash"><dt>SHA-256</dt><dd :title="latestResultRef.checksum_sha256">{{ shortHash(latestResultRef.checksum_sha256) }}</dd></div>
      </dl>
    </section>

    <section class="history-section">
      <header>
        <div>
          <strong>导入证据历史</strong>
          <small>最近 20 个不可变批次</small>
        </div>
        <a-button size="small" :loading="loadingHistoryRef" @click="workbookStore.loadHistory()">
          刷新
        </a-button>
      </header>
      <a-spin :spinning="loadingHistoryRef">
        <div v-if="historyRef?.items.length" class="history-list">
          <article v-for="item in historyRef.items" :key="item.batch_code">
            <div class="history-title">
              <strong>{{ item.original_filename }}</strong>
              <span>{{ formatTime(item.imported_at) }}</span>
            </div>
            <p>{{ item.import_comment }}</p>
            <footer>
              <span>{{ item.imported_by }} · {{ item.imported_by_role }}</span>
              <span>{{ item.row_count }} 行 / 更新 {{ item.changed_count }}</span>
              <span :title="item.checksum_sha256">SHA {{ shortHash(item.checksum_sha256) }}</span>
            </footer>
          </article>
        </div>
        <a-empty v-else description="尚无属性工作簿导入记录" />
      </a-spin>
    </section>
  </a-modal>
</template>

<style scoped lang="less">
.workflow-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin-top: 16px;
}

.workflow-card {
  display: flex;
  min-height: 388px;
  padding: 16px;
  border: 1px solid #dfe6e2;
  border-radius: 8px;
  flex-direction: column;
  gap: 14px;
}

.workflow-card > header,
.history-section > header,
.result-card > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.workflow-card > header {
  justify-content: flex-start;
  gap: 10px;
}

.workflow-card header div,
.history-section header div {
  display: flex;
  flex-direction: column;
}

.workflow-card small,
.history-section small {
  color: #7b8781;
  font-size: 10px;
}

.step-index {
  display: grid;
  width: 28px;
  height: 28px;
  color: #fff;
  background: #315f48;
  border-radius: 50%;
  place-items: center;
}

.scope-options {
  display: grid;
  gap: 10px;
}

.scope-options :deep(.ant-radio-wrapper) {
  align-items: flex-start;
  padding: 8px;
  border: 1px solid #e3e8e5;
  border-radius: 6px;
}

.scope-options small { display: block; margin-top: 2px; }
.range-count { color: #6c7872; font-size: 10px; text-align: right; }
.range-count.invalid { color: #cf3f32; }
.workflow-card > .ant-btn { margin-top: auto; }

.comment-field {
  display: flex;
  gap: 6px;
  flex-direction: column;
  font-size: 11px;
}

.comment-field b { color: #cf3f32; }
.operator-row { display: flex; justify-content: space-between; font-size: 11px; }
.operator-row span { color: #7b8781; }

.result-card {
  padding: 13px 15px;
  margin-top: 14px;
  background: #f5f9f6;
  border: 1px solid #dce8e0;
  border-radius: 8px;
}

.result-card dl {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px 14px;
  margin: 10px 0 0;
}

.result-card dl div { min-width: 0; }
.result-card dt { color: #7a8780; font-size: 9px; }
.result-card dd { margin: 2px 0 0; font-size: 11px; overflow: hidden; text-overflow: ellipsis; }
.result-card .hash { grid-column: span 2; }

.history-section { margin-top: 16px; }
.history-list { max-height: 220px; margin-top: 8px; overflow: auto; }
.history-list article { padding: 10px 0; border-top: 1px solid #e5e9e7; }
.history-title { display: flex; justify-content: space-between; gap: 10px; }
.history-title span, .history-list p, .history-list footer { color: #748079; font-size: 10px; }
.history-list p { margin: 4px 0; }
.history-list footer { display: flex; gap: 16px; flex-wrap: wrap; }

@media (max-width: 860px) {
  .workflow-grid { grid-template-columns: 1fr; }
  .result-card dl { grid-template-columns: 1fr 1fr; }
}
</style>
