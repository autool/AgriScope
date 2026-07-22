<script setup lang="ts">
import { InboxOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import type { UploadProps } from 'ant-design-vue'
import { computed, ref, watch } from 'vue'

import type {
  DisasterGeoJsonImportPayload,
  DisasterImportProperties,
  GeoJsonFeature,
} from '@/types/workbench'

interface DisasterImportModalProps {
  open: boolean
  loading: boolean
}

const props = defineProps<DisasterImportModalProps>()
const emit = defineEmits<{
  cancel: []
  submit: [payload: Omit<DisasterGeoJsonImportPayload, 'operator_code'>]
}>()

const fileNameRef = ref<string>('')
const sourceNameRef = ref<string>('')
const sourceUriRef = ref<string>('')
const sourceVersionRef = ref<string>('')
const conflictPolicyRef = ref<'reject' | 'replace'>('reject')
const commentRef = ref<string>('')
const featuresRef = ref<Array<GeoJsonFeature<DisasterImportProperties>>>([])

const canSubmitComputed = computed<boolean>(() => (
  featuresRef.value.length > 0
  && Boolean(sourceNameRef.value.trim())
  && Boolean(sourceUriRef.value.trim())
  && Boolean(sourceVersionRef.value.trim())
  && Boolean(commentRef.value.trim())
))

const resetForm = (): void => {
  fileNameRef.value = ''
  sourceNameRef.value = ''
  sourceUriRef.value = ''
  sourceVersionRef.value = ''
  conflictPolicyRef.value = 'reject'
  commentRef.value = ''
  featuresRef.value = []
}

const isRecord = (value: unknown): value is Record<string, unknown> => (
  typeof value === 'object' && value !== null && !Array.isArray(value)
)

/**
 * 读取本地 GeoJSON 并完成上传前的轻量结构检查。
 * Args:
 *   file: 用户选择的 JSON/GeoJSON 文件。
 * Returns:
 *   Promise<boolean>: 始终返回 false，阻止组件直接上传文件。
 */
const beforeUpload: UploadProps['beforeUpload'] = async (file) => {
  try {
    if (file.size > 20 * 1024 * 1024) {
      throw new Error('单个 GeoJSON 文件不得超过 20MB')
    }
    const parsed = JSON.parse(await file.text()) as unknown
    if (!isRecord(parsed) || parsed.type !== 'FeatureCollection') {
      throw new Error('文件必须是 GeoJSON FeatureCollection')
    }
    if (!Array.isArray(parsed.features) || parsed.features.length === 0) {
      throw new Error('GeoJSON 至少包含一个 Feature')
    }
    if (parsed.features.length > 500) {
      throw new Error('单次最多导入 500 个灾害斑块')
    }
    parsed.features.forEach((feature, index) => {
      if (!isRecord(feature) || feature.type !== 'Feature') {
        throw new Error(`第 ${index + 1} 个要素不是标准 Feature`)
      }
      const geometry = feature.geometry
      const properties = feature.properties
      if (!isRecord(geometry) || geometry.type !== 'Polygon') {
        throw new Error(`第 ${index + 1} 个要素必须使用 Polygon 几何`)
      }
      if (!isRecord(properties)) {
        throw new Error(`第 ${index + 1} 个要素缺少 properties`)
      }
      const requiredFields = [
        'patch_code',
        'source_feature_id',
        'disaster_type',
        'severity',
        'detected_at',
      ]
      const missing = requiredFields.find((field) => !properties[field])
      if (missing) {
        throw new Error(`第 ${index + 1} 个要素缺少 ${missing}`)
      }
    })
    featuresRef.value = parsed.features as Array<
      GeoJsonFeature<DisasterImportProperties>
    >
    fileNameRef.value = file.name
    sourceNameRef.value ||= file.name.replace(/\.(geojson|json)$/i, '')
    message.success(`已读取 ${featuresRef.value.length} 个灾害斑块`)
  } catch (error) {
    featuresRef.value = []
    fileNameRef.value = ''
    message.error(error instanceof Error ? error.message : 'GeoJSON 文件解析失败')
  }
  return false
}

const handleSubmit = (): void => {
  if (!canSubmitComputed.value) return
  emit('submit', {
    type: 'FeatureCollection',
    source_name: sourceNameRef.value.trim(),
    source_uri: sourceUriRef.value.trim(),
    source_version: sourceVersionRef.value.trim(),
    conflict_policy: conflictPolicyRef.value,
    comment: commentRef.value.trim(),
    features: featuresRef.value,
  })
}

watch(
  () => props.open,
  (open) => {
    if (!open) resetForm()
  },
)
</script>

<template>
  <a-modal
    :open="props.open"
    title="导入灾害模型 GeoJSON"
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
      message="导入要求"
      description="仅接受 EPSG:4326 Polygon。面积由 PostGIS 重新计算，超出项目省域、几何无效、编号或来源要素重复时整批回滚。"
    />

    <a-upload-dragger
      class="geojson-upload"
      accept=".geojson,.json,application/geo+json,application/json"
      :before-upload="beforeUpload"
      :file-list="[]"
      :max-count="1"
    >
      <p class="ant-upload-drag-icon"><InboxOutlined /></p>
      <p class="ant-upload-text">选择或拖入灾害模型 GeoJSON</p>
      <p class="ant-upload-hint">
        properties 必须包含 patch_code、source_feature_id、disaster_type、severity、detected_at
      </p>
    </a-upload-dragger>

    <div v-if="fileNameRef" class="file-summary">
      <strong>{{ fileNameRef }}</strong>
      <span>{{ featuresRef.length }} 个 Polygon 要素待校验</span>
    </div>

    <div class="form-grid">
      <label>
        <span>模型或数据源名称</span>
        <a-input v-model:value="sourceNameRef" placeholder="例如：省级洪涝识别模型" />
      </label>
      <label>
        <span>来源版本</span>
        <a-input v-model:value="sourceVersionRef" placeholder="例如：flood-v2.3-20260722" />
      </label>
      <label class="full-row">
        <span>来源 URI</span>
        <a-input
          v-model:value="sourceUriRef"
          placeholder="例如：model://flood-v2/runs/20260722 或受控文件地址"
        />
      </label>
      <label class="full-row">
        <span>编号冲突策略</span>
        <a-radio-group v-model:value="conflictPolicyRef">
          <a-radio value="reject">发现重复时整批拒绝</a-radio>
          <a-radio value="replace">按相同 patch_code 替换并重置复核状态</a-radio>
        </a-radio-group>
      </label>
      <label class="full-row">
        <span>导入依据</span>
        <a-textarea
          v-model:value="commentRef"
          :rows="2"
          placeholder="说明模型运行批次、影像日期、阈值或成果文件交接依据"
        />
      </label>
    </div>
  </a-modal>
</template>

<style scoped>
.geojson-upload { display: block; margin-top: 12px; }
.file-summary { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; margin-top: 8px; font-size: 11px; color: #315b46; background: #f1f7f3; border: 1px solid #dce9e1; border-radius: 5px; }
.file-summary span { font-size: 9px; color: #718078; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 12px; }
.form-grid label { display: flex; flex-direction: column; gap: 4px; }
.form-grid label > span { font-size: 9px; color: #64736b; }
.form-grid .full-row { grid-column: 1 / -1; }
:deep(.ant-upload-hint) { padding: 0 20px; font-size: 9px; }
</style>
