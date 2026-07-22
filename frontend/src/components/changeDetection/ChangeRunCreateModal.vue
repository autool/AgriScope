<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type {
  ChangeImagery,
  ChangeRunCreatePayload,
} from '@/types/changeDetection'
import type { ImageryRegistrationJob } from '@/types/imageryRegistration'

const props = defineProps<{
  open: boolean
  imagery: ChangeImagery[]
  registrations: ImageryRegistrationJob[]
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
const registrationJobCodeRef = ref<string>('')

const eligibleImageryComputed = computed<ChangeImagery[]>(() => (
  props.imagery.filter((asset) => asset.eligible)
))

const matchingRegistrationsComputed = computed<ImageryRegistrationJob[]>(() => (
  props.registrations.filter(job => (
    job.artifact_verified
    && job.reference_asset_code === baselineAssetCodeRef.value
    && job.moving_asset_code === targetAssetCodeRef.value
  ))
))

const canSubmitComputed = computed<boolean>(() => Boolean(
  props.operatorCode
  && runCodeRef.value.trim()
  && runNameRef.value.trim()
  && baselineAssetCodeRef.value
  && targetAssetCodeRef.value
  && baselineAssetCodeRef.value !== targetAssetCodeRef.value
  && matchingRegistrationsComputed.value.some(
    job => job.job_code === registrationJobCodeRef.value,
  ),
))

const submit = (): void => {
  if (!canSubmitComputed.value || !props.operatorCode) return
  emit('create', {
    run_code: runCodeRef.value.trim(),
    run_name: runNameRef.value.trim(),
    baseline_asset_code: baselineAssetCodeRef.value,
    target_asset_code: targetAssetCodeRef.value,
    registration_job_code: registrationJobCodeRef.value,
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
    registrationJobCodeRef.value = ''
  },
)

watch(
  () => [baselineAssetCodeRef.value, targetAssetCodeRef.value],
  () => {
    registrationJobCodeRef.value = matchingRegistrationsComputed.value[0]?.job_code || ''
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
      <a-form-item label="实体配准成果" required>
        <a-select
          v-model:value="registrationJobCodeRef"
          :disabled="!baselineAssetCodeRef || !targetAssetCodeRef"
          placeholder="选择与两期影像完全匹配的配准成果"
        >
          <a-select-option
            v-for="job in matchingRegistrationsComputed"
            :key="job.job_code"
            :value="job.job_code"
          >
            {{ job.job_name }} · 残差 {{ job.residual_offset_pixels.toFixed(4) }} px ·
            SHA {{ job.checksum_sha256.slice(0, 12) }}…
          </a-select-option>
        </a-select>
      </a-form-item>
      <a-alert
        v-if="baselineAssetCodeRef && targetAssetCodeRef && !matchingRegistrationsComputed.length"
        type="warning"
        show-icon
        message="所选两期影像没有通过实体残差门禁的配准成果"
        description="请先在影像预处理页完成双景自动配准；不能再手工填写偏差和证据 URI。"
      />
    </a-form>
  </a-modal>
</template>

<style scoped>
.run-form { margin-top: 14px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; }
</style>
