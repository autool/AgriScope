<script setup lang="ts">
import { computed, reactive, ref } from 'vue'

import type {
  SupervisionInspectionConclusion,
  SupervisionInspectionCreatePayload,
  SupervisionInspectionStage,
} from '@/types/supervision'

const props = defineProps<{
  planCode: string
  operatorCode: string | null
  saving: boolean
}>()

const emit = defineEmits<{
  create: [payload: SupervisionInspectionCreatePayload]
}>()

const openRef = ref<boolean>(false)
const formRef = reactive({
  inspectionCode: '',
  inspectionStage: 'plot_interpretation' as SupervisionInspectionStage,
  inspectedAt: '',
  conclusion: 'conditional' as SupervisionInspectionConclusion,
  evidenceUri: '',
  summary: '',
})

const canSubmitComputed = computed<boolean>(() => Boolean(
  props.operatorCode
  && formRef.inspectionCode.trim()
  && formRef.inspectedAt
  && formRef.evidenceUri.trim()
  && formRef.summary.trim(),
))

const open = (): void => { openRef.value = true }
const close = (): void => { openRef.value = false }

const submit = (): void => {
  if (!canSubmitComputed.value || !props.operatorCode) return
  emit('create', {
    inspection_code: formRef.inspectionCode.trim(),
    inspection_stage: formRef.inspectionStage,
    inspected_at: formRef.inspectedAt,
    conclusion: formRef.conclusion,
    evidence_uri: formRef.evidenceUri.trim(),
    summary: formRef.summary.trim(),
    operator_code: props.operatorCode,
  })
}

defineExpose({ open, close })
</script>

<template>
  <a-modal
    v-model:open="openRef"
    :title="`登记过程检查 · ${planCode}`"
    width="650px"
    :confirm-loading="saving"
    :ok-button-props="{ disabled: !canSubmitComputed }"
    @ok="submit"
  >
    <a-alert
      type="info"
      show-icon
      message="检查证据独立于自动质检和三级审核"
      description="请填写可追溯的档案、照片、记录表或服务地址；仅独立监理身份可登记过程检查。"
    />
    <a-form layout="vertical" class="inspection-form">
      <div class="form-grid">
        <a-form-item label="检查编号" required>
          <a-input v-model:value="formRef.inspectionCode" placeholder="例如 INSP-2026-001" />
        </a-form-item>
        <a-form-item label="检查环节" required>
          <a-select v-model:value="formRef.inspectionStage">
            <a-select-option value="imagery_processing">影像生产</a-select-option>
            <a-select-option value="plot_interpretation">地块解译</a-select-option>
            <a-select-option value="quality_control">质量控制</a-select-option>
            <a-select-option value="field_verification">外业核查</a-select-option>
            <a-select-option value="review_delivery">审核交付</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="检查时间" required>
          <a-date-picker
            v-model:value="formRef.inspectedAt"
            show-time
            value-format="YYYY-MM-DDTHH:mm:ssZ"
            style="width: 100%"
          />
        </a-form-item>
        <a-form-item label="检查结论" required>
          <a-select v-model:value="formRef.conclusion">
            <a-select-option value="passed">通过</a-select-option>
            <a-select-option value="conditional">有条件通过</a-select-option>
            <a-select-option value="failed">不通过</a-select-option>
          </a-select>
        </a-form-item>
      </div>
      <a-form-item label="证据地址" required>
        <a-input v-model:value="formRef.evidenceUri" placeholder="archive://、storage:// 或受控业务系统地址" />
      </a-form-item>
      <a-form-item label="检查摘要" required>
        <a-textarea v-model:value="formRef.summary" :rows="4" placeholder="记录检查范围、方法、事实和结论依据" />
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<style scoped>
.inspection-form { margin-top: 14px; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 12px; }
</style>
