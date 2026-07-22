<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type { ChangeCandidateImportPayload } from '@/types/changeDetection'

const props = defineProps<{
  open: boolean
  runCode: string
  operatorCode: string | null
  saving: boolean
}>()

const emit = defineEmits<{
  close: []
  import: [payload: ChangeCandidateImportPayload]
}>()

const sourceNameRef = ref<string>('')
const sourceUriRef = ref<string>('')
const sourceVersionRef = ref<string>('')
const commentRef = ref<string>('')
const featuresRef = ref<unknown[]>([])
const fileNameRef = ref<string>('')
const fileErrorRef = ref<string>('')

const canSubmitComputed = computed<boolean>(() => Boolean(
  props.operatorCode
  && sourceNameRef.value.trim()
  && sourceUriRef.value.trim()
  && sourceVersionRef.value.trim()
  && commentRef.value.trim()
  && featuresRef.value.length > 0,
))

const selectFile = async (event: Event): Promise<void> => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  fileErrorRef.value = ''
  featuresRef.value = []
  fileNameRef.value = file?.name || ''
  if (!file) return
  if (file.size > 10 * 1024 * 1024) {
    fileErrorRef.value = 'GeoJSON 文件不得超过 10 MB'
    return
  }
  try {
    const payload = JSON.parse(await file.text()) as {
      type?: unknown
      features?: unknown
    }
    if (payload.type !== 'FeatureCollection' || !Array.isArray(payload.features)) {
      fileErrorRef.value = '文件必须是标准 GeoJSON FeatureCollection'
      return
    }
    if (payload.features.length < 1 || payload.features.length > 500) {
      fileErrorRef.value = '单批候选数量必须为 1–500 个'
      return
    }
    featuresRef.value = payload.features
  } catch {
    fileErrorRef.value = 'GeoJSON 文件无法解析'
  }
}

const submit = (): void => {
  if (!canSubmitComputed.value || !props.operatorCode) return
  emit('import', {
    type: 'FeatureCollection',
    source_name: sourceNameRef.value.trim(),
    source_uri: sourceUriRef.value.trim(),
    source_version: sourceVersionRef.value.trim(),
    operator_code: props.operatorCode,
    comment: commentRef.value.trim(),
    features: featuresRef.value,
  })
}

watch(
  () => props.open,
  (open) => {
    if (!open) return
    sourceNameRef.value = ''
    sourceUriRef.value = ''
    sourceVersionRef.value = ''
    commentRef.value = ''
    featuresRef.value = []
    fileNameRef.value = ''
    fileErrorRef.value = ''
  },
)
</script>

<template>
  <a-modal
    :open="open"
    :title="`导入变化候选 · ${runCode}`"
    :confirm-loading="saving"
    :ok-button-props="{ disabled: !canSubmitComputed }"
    width="620px"
    @cancel="emit('close')"
    @ok="submit"
  >
    <a-alert
      type="info"
      show-icon
      message="服务端将原子校验完整批次"
      description="仅接受 EPSG:4326 Polygon；服务端重算面积、校验省域范围和当前任务固化的 200/400㎡ 最小图斑规则，任一候选失败则整批回滚。"
    />
    <a-form layout="vertical" class="import-form">
      <div class="form-grid">
        <a-form-item label="来源名称" required>
          <a-input v-model:value="sourceNameRef" placeholder="模型或生产工具名称" />
        </a-form-item>
        <a-form-item label="来源版本" required>
          <a-input v-model:value="sourceVersionRef" placeholder="例如 model-v2.1" />
        </a-form-item>
      </div>
      <a-form-item label="来源 URI" required>
        <a-input v-model:value="sourceUriRef" placeholder="实体结果文件或可追溯地址" />
      </a-form-item>
      <a-form-item label="候选 GeoJSON 文件" required>
        <input type="file" accept=".geojson,.json,application/geo+json,application/json" @change="selectFile">
        <div class="file-state" :class="{ error: fileErrorRef }">
          {{ fileErrorRef || (fileNameRef ? `${fileNameRef} · ${featuresRef.length} 个候选` : '尚未选择文件') }}
        </div>
      </a-form-item>
      <a-form-item label="导入说明" required>
        <a-textarea
          v-model:value="commentRef"
          :rows="3"
          placeholder="说明模型、参数、处理批次和复核用途"
        />
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<style scoped>
.import-form { margin-top: 14px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; }
.file-state { margin-top: 5px; font-size: 11px; color: #5f766a; }
.file-state.error { color: #c94f3d; }
</style>
