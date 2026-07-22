<script setup lang="ts">
import { computed, reactive, ref } from 'vue'

import type {
  SupervisionFindingCreatePayload,
  SupervisionFindingSeverity,
  SupervisionWorkArea,
} from '@/types/supervision'

const props = defineProps<{
  planCode: string
  inspectionCode: string
  regionCodes: string[]
  workAreas: SupervisionWorkArea[]
  operatorCode: string | null
  saving: boolean
}>()

const emit = defineEmits<{
  create: [payload: SupervisionFindingCreatePayload]
}>()

const openRef = ref<boolean>(false)
const formRef = reactive({
  findingCode: '',
  plotCode: '',
  regionCode: '',
  issueType: '',
  severity: 'major' as SupervisionFindingSeverity,
  description: '',
  evidenceUri: '',
  reworkDeadline: '',
})

const regionOptionsComputed = computed(() => (
  props.workAreas.filter((area) => props.regionCodes.includes(area.region_code))
))

const canSubmitComputed = computed<boolean>(() => Boolean(
  props.operatorCode
  && formRef.findingCode.trim()
  && formRef.regionCode
  && formRef.issueType.trim()
  && formRef.description.trim()
  && formRef.evidenceUri.trim()
  && formRef.reworkDeadline,
))

const open = (): void => { openRef.value = true }
const close = (): void => { openRef.value = false }

const submit = (): void => {
  if (!canSubmitComputed.value || !props.operatorCode) return
  emit('create', {
    finding_code: formRef.findingCode.trim(),
    plot_code: formRef.plotCode.trim() || null,
    region_code: formRef.regionCode,
    issue_type: formRef.issueType.trim(),
    severity: formRef.severity,
    description: formRef.description.trim(),
    evidence_uri: formRef.evidenceUri.trim(),
    rework_deadline: formRef.reworkDeadline,
    operator_code: props.operatorCode,
  })
}

defineExpose({ open, close })
</script>

<template>
  <a-modal
    v-model:open="openRef"
    :title="`登记监理问题 · ${inspectionCode}`"
    width="680px"
    :confirm-loading="saving"
    :ok-button-props="{ disabled: !canSubmitComputed }"
    @ok="submit"
  >
    <a-form layout="vertical">
      <div class="form-grid">
        <a-form-item label="问题编号" required>
          <a-input v-model:value="formRef.findingCode" placeholder="例如 FIND-2026-001" />
        </a-form-item>
        <a-form-item label="严重度" required>
          <a-select v-model:value="formRef.severity">
            <a-select-option value="minor">一般</a-select-option>
            <a-select-option value="major">重要</a-select-option>
            <a-select-option value="critical">严重</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="县区" required>
          <a-select v-model:value="formRef.regionCode" show-search option-filter-prop="label">
            <a-select-option
              v-for="area in regionOptionsComputed"
              :key="area.region_code"
              :value="area.region_code"
              :label="`${area.city_name} / ${area.region_name}`"
            >
              {{ area.city_name }} / {{ area.region_name }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="关联样本图斑（可选）">
          <a-input v-model:value="formRef.plotCode" placeholder="必须属于本计划显式样本" />
        </a-form-item>
        <a-form-item label="问题类型" required>
          <a-input v-model:value="formRef.issueType" placeholder="例如 边界偏差、证据缺失、流程违规" />
        </a-form-item>
        <a-form-item label="整改期限" required>
          <a-date-picker v-model:value="formRef.reworkDeadline" value-format="YYYY-MM-DD" style="width: 100%" />
        </a-form-item>
      </div>
      <a-form-item label="问题证据地址" required>
        <a-input v-model:value="formRef.evidenceUri" placeholder="可追溯照片、记录表、档案或系统地址" />
      </a-form-item>
      <a-form-item label="问题描述" required>
        <a-textarea v-model:value="formRef.description" :rows="4" placeholder="记录检查事实、影响范围和整改要求" />
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<style scoped>
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 12px; }
</style>
