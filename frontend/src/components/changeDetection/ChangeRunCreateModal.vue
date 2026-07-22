<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type {
  ChangeImagery,
  ChangeRunCreatePayload,
} from '@/types/changeDetection'

const props = defineProps<{
  open: boolean
  imagery: ChangeImagery[]
  operatorCode: string | null
  saving: boolean
}>()

const emit = defineEmits<{
  close: []
  create: [payload: ChangeRunCreatePayload]
}>()

const runCodeRef = ref<string>('')
const runNameRef = ref<string>('')
const baselineAssetCodeRef = ref<string>('')
const targetAssetCodeRef = ref<string>('')
const alignmentMethodRef = ref<string>('同名点与道路交叉点联合配准')
const alignmentOffsetPixelsRef = ref<number>(1)
const alignmentEvidenceUriRef = ref<string>('')

const eligibleImageryComputed = computed<ChangeImagery[]>(() => (
  props.imagery.filter((asset) => asset.eligible)
))

const canSubmitComputed = computed<boolean>(() => Boolean(
  props.operatorCode
  && runCodeRef.value.trim()
  && runNameRef.value.trim()
  && baselineAssetCodeRef.value
  && targetAssetCodeRef.value
  && baselineAssetCodeRef.value !== targetAssetCodeRef.value
  && alignmentMethodRef.value.trim()
  && alignmentEvidenceUriRef.value.trim(),
))

const submit = (): void => {
  if (!canSubmitComputed.value || !props.operatorCode) return
  emit('create', {
    run_code: runCodeRef.value.trim(),
    run_name: runNameRef.value.trim(),
    baseline_asset_code: baselineAssetCodeRef.value,
    target_asset_code: targetAssetCodeRef.value,
    alignment_method: alignmentMethodRef.value.trim(),
    alignment_offset_pixels: alignmentOffsetPixelsRef.value,
    alignment_evidence_uri: alignmentEvidenceUriRef.value.trim(),
    operator_code: props.operatorCode,
  })
}

watch(
  () => props.open,
  (open) => {
    if (!open) return
    runCodeRef.value = `CD-${new Date().toISOString().slice(0, 10).replaceAll('-', '')}`
    runNameRef.value = ''
    baselineAssetCodeRef.value = ''
    targetAssetCodeRef.value = ''
    alignmentOffsetPixelsRef.value = 1
    alignmentEvidenceUriRef.value = ''
  },
)
</script>

<template>
  <a-modal
    :open="open"
    title="创建多时相变化检测任务"
    :confirm-loading="saving"
    :ok-button-props="{ disabled: !canSubmitComputed }"
    width="620px"
    @cancel="emit('close')"
    @ok="submit"
  >
    <a-alert
      v-if="eligibleImageryComputed.length < 2"
      type="warning"
      show-icon
      message="至少需要两期可用业务影像"
      description="影像必须具备实体文件和 SHA-256，并完成辐射定标及几何/大气校正。"
    />
    <a-form layout="vertical" class="run-form">
      <div class="form-grid">
        <a-form-item label="检测任务编号" required>
          <a-input v-model:value="runCodeRef" />
        </a-form-item>
        <a-form-item label="任务名称" required>
          <a-input v-model:value="runNameRef" placeholder="例如：七月耕地变化检测" />
        </a-form-item>
        <a-form-item label="前时相影像" required>
          <a-select v-model:value="baselineAssetCodeRef" placeholder="选择较早影像">
            <a-select-option
              v-for="asset in eligibleImageryComputed"
              :key="asset.asset_code"
              :value="asset.asset_code"
              :disabled="asset.asset_code === targetAssetCodeRef"
            >
              {{ asset.asset_name }} · {{ asset.acquired_at.slice(0, 10) }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="后时相影像" required>
          <a-select v-model:value="targetAssetCodeRef" placeholder="选择较晚影像">
            <a-select-option
              v-for="asset in eligibleImageryComputed"
              :key="asset.asset_code"
              :value="asset.asset_code"
              :disabled="asset.asset_code === baselineAssetCodeRef"
            >
              {{ asset.asset_name }} · {{ asset.acquired_at.slice(0, 10) }}
            </a-select-option>
          </a-select>
        </a-form-item>
      </div>
      <a-form-item label="配准方法" required>
        <a-input v-model:value="alignmentMethodRef" />
      </a-form-item>
      <div class="alignment-row">
        <a-form-item label="配准偏差（像素）" required>
          <a-input-number
            v-model:value="alignmentOffsetPixelsRef"
            :min="0"
            :max="1000"
            :precision="3"
          />
        </a-form-item>
        <a-form-item label="配准证据 URI" required>
          <a-input
            v-model:value="alignmentEvidenceUriRef"
            placeholder="storage://alignment/run-001/report.json"
          />
        </a-form-item>
      </div>
    </a-form>
  </a-modal>
</template>

<style scoped>
.run-form { margin-top: 14px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; }
.alignment-row { display: grid; grid-template-columns: 160px 1fr; gap: 12px; }
.alignment-row :deep(.ant-input-number) { width: 100%; }
</style>
