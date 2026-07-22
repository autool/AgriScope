<script setup lang="ts">
import { DownloadOutlined, InboxOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import type { UploadProps } from 'ant-design-vue'
import { computed, ref, watch } from 'vue'

import type { AreaStatisticsHistoryImportMetadata } from '@/types/workbench'

interface StatisticsHistoryImportModalProps {
  open: boolean
  loading: boolean
  monitorYear: number | null
}

const props = defineProps<StatisticsHistoryImportModalProps>()
const emit = defineEmits<{
  cancel: []
  submit: [
    file: File,
    metadata: Omit<AreaStatisticsHistoryImportMetadata, 'operator_code'>,
  ]
  downloadTemplate: []
}>()

const fileRef = ref<File | null>(null)
const sourceNameRef = ref<string>('')
const sourceUriRef = ref<string>('')
const sourceVersionRef = ref<string>('')
const commentRef = ref<string>('')
const conflictStrategyRef = ref<'reject' | 'replace'>('reject')

const canSubmitComputed = computed<boolean>(() => (
  Boolean(fileRef.value)
  && Boolean(sourceNameRef.value.trim())
  && Boolean(sourceUriRef.value.trim())
  && Boolean(sourceVersionRef.value.trim())
  && Boolean(commentRef.value.trim())
))

const resetForm = (): void => {
  fileRef.value = null
  sourceNameRef.value = ''
  sourceUriRef.value = ''
  sourceVersionRef.value = ''
  commentRef.value = ''
  conflictStrategyRef.value = 'reject'
}

const beforeUpload: UploadProps['beforeUpload'] = (file) => {
  if (!file.name.toLocaleLowerCase().endsWith('.csv')) {
    message.error('历史年度统计仅支持 .csv 文件')
    return false
  }
  if (file.size > 1024 * 1024) {
    message.error('历史年度统计 CSV 不得超过 1MB')
    return false
  }
  fileRef.value = file
  sourceNameRef.value ||= file.name.replace(/\.csv$/i, '')
  message.success('已选择历史年度统计文件，提交后由服务端校验')
  return false
}

const handleSubmit = (): void => {
  if (!fileRef.value || !canSubmitComputed.value) return
  emit('submit', fileRef.value, {
    source_name: sourceNameRef.value.trim(),
    source_uri: sourceUriRef.value.trim(),
    source_version: sourceVersionRef.value.trim(),
    comment: commentRef.value.trim(),
    conflict_strategy: conflictStrategyRef.value,
  })
}

watch(() => props.open, (open) => {
  if (!open) resetForm()
})
</script>

<template>
  <a-modal
    :open="props.open"
    title="导入真实历史年度统计"
    width="640px"
    :confirm-loading="props.loading"
    :ok-button-props="{ disabled: !canSubmitComputed }"
    ok-text="校验并导入"
    cancel-text="取消"
    @ok="handleSubmit"
    @cancel="emit('cancel')"
  >
    <a-alert
      type="info"
      show-icon
      message="只接受当前监测年度之前的真实统计成果"
      :description="`当前监测年度为 ${props.monitorYear || '--'}。CSV 必须提供 monitor_year、total_area_ha、farmland_area_ha、crop_area_ha；原始文件 SHA256 和项目负责人角色将写入审计。`"
    />
    <div class="template-row">
      <span>单次最多 30 个年度 · UTF-8 CSV</span>
      <a-button size="small" @click="emit('downloadTemplate')">
        <DownloadOutlined />下载模板
      </a-button>
    </div>
    <a-upload-dragger
      accept=".csv,text/csv"
      :before-upload="beforeUpload"
      :file-list="[]"
      :max-count="1"
    >
      <p class="ant-upload-drag-icon"><InboxOutlined /></p>
      <p class="ant-upload-text">选择或拖入历史年度统计 CSV</p>
      <p class="ant-upload-hint">当前文件：{{ fileRef?.name || '尚未选择' }}</p>
    </a-upload-dragger>
    <div class="form-grid">
      <label>
        <span>统计成果来源</span>
        <a-input v-model:value="sourceNameRef" placeholder="例如：2025 年农业农村统计年报" />
      </label>
      <label>
        <span>来源版本</span>
        <a-input v-model:value="sourceVersionRef" placeholder="例如：final-v1" />
      </label>
      <label class="full-row">
        <span>来源 URI</span>
        <a-input v-model:value="sourceUriRef" placeholder="例如：archive://statistics/2025/final.csv" />
      </label>
      <label class="full-row">
        <span>年度冲突策略</span>
        <a-radio-group v-model:value="conflictStrategyRef">
          <a-radio value="reject">发现已有年度时整批拒绝</a-radio>
          <a-radio value="replace">保留旧批次审计并替换当前快照</a-radio>
        </a-radio-group>
      </label>
      <label class="full-row">
        <span>导入依据</span>
        <a-textarea
          v-model:value="commentRef"
          :rows="2"
          placeholder="说明统计成果批次、审批/盖章状态和文件交接依据"
        />
      </label>
    </div>
  </a-modal>
</template>

<style scoped>
.template-row { display: flex; align-items: center; justify-content: space-between; margin: 10px 0 6px; font-size: 9px; color: #718078; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 12px; }
.form-grid label { display: flex; flex-direction: column; gap: 4px; }
.form-grid label > span { font-size: 9px; color: #64736b; }
.form-grid .full-row { grid-column: 1 / -1; }
:deep(.ant-upload-hint) { padding: 0 18px; font-size: 9px; }
</style>
