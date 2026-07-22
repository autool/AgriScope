<script setup lang="ts">
import { computed, reactive, ref } from 'vue'

import type {
  SupervisionCountyEvaluation,
  SupervisionCountyEvaluationPayload,
  SupervisionWorkArea,
} from '@/types/supervision'

const props = defineProps<{
  planCode: string
  regionCodes: string[]
  workAreas: SupervisionWorkArea[]
  evaluations: SupervisionCountyEvaluation[]
  operatorCode: string | null
  saving: boolean
}>()

const emit = defineEmits<{
  evaluate: [regionCode: string, payload: SupervisionCountyEvaluationPayload]
}>()

const openRef = ref<boolean>(false)
const formRef = reactive({
  regionCode: '',
  qualityScore: 90,
  timelinessScore: 90,
  complianceScore: 90,
  comment: '',
})

const optionsComputed = computed(() => (
  props.workAreas.filter((area) => props.regionCodes.includes(area.region_code))
))
const overallScoreComputed = computed<number>(() => Number((
  formRef.qualityScore * 0.5
  + formRef.timelinessScore * 0.25
  + formRef.complianceScore * 0.25
).toFixed(2)))
const canSubmitComputed = computed<boolean>(() => Boolean(
  props.operatorCode && formRef.regionCode && formRef.comment.trim(),
))

const loadExisting = (): void => {
  const existing = props.evaluations.find((item) => item.region_code === formRef.regionCode)
  if (!existing) return
  formRef.qualityScore = existing.quality_score
  formRef.timelinessScore = existing.timeliness_score
  formRef.complianceScore = existing.compliance_score
  formRef.comment = existing.comment
}

const open = (): void => { openRef.value = true }
const close = (): void => { openRef.value = false }
const submit = (): void => {
  if (!canSubmitComputed.value || !props.operatorCode) return
  emit('evaluate', formRef.regionCode, {
    quality_score: formRef.qualityScore,
    timeliness_score: formRef.timelinessScore,
    compliance_score: formRef.complianceScore,
    comment: formRef.comment.trim(),
    operator_code: props.operatorCode,
  })
}

defineExpose({ open, close })
</script>

<template>
  <a-modal
    v-model:open="openRef"
    :title="`县区监理评价 · ${planCode}`"
    width="620px"
    :confirm-loading="saving"
    :ok-button-props="{ disabled: !canSubmitComputed }"
    @ok="submit"
  >
    <a-form layout="vertical">
      <a-form-item label="县区" required>
        <a-select
          v-model:value="formRef.regionCode"
          show-search
          option-filter-prop="label"
          @change="loadExisting"
        >
          <a-select-option
            v-for="area in optionsComputed"
            :key="area.region_code"
            :value="area.region_code"
            :label="`${area.city_name} / ${area.region_name}`"
          >
            {{ area.city_name }} / {{ area.region_name }}
          </a-select-option>
        </a-select>
      </a-form-item>
      <div class="score-grid">
        <a-form-item label="质量得分（50%）" required>
          <a-input-number
            v-model:value="formRef.qualityScore"
            :min="0"
            :max="100"
            style="width: 100%"
          />
        </a-form-item>
        <a-form-item label="时效得分（25%）" required>
          <a-input-number
            v-model:value="formRef.timelinessScore"
            :min="0"
            :max="100"
            style="width: 100%"
          />
        </a-form-item>
        <a-form-item label="合规得分（25%）" required>
          <a-input-number
            v-model:value="formRef.complianceScore"
            :min="0"
            :max="100"
            style="width: 100%"
          />
        </a-form-item>
      </div>
      <a-alert type="info" show-icon :message="`服务端将按固定权重计算综合得分：${overallScoreComputed}`" />
      <a-form-item label="评价依据" required class="comment-field">
        <a-textarea v-model:value="formRef.comment" :rows="4" placeholder="说明评分证据、扣分项和县区整改表现" />
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<style scoped>
.score-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0 10px; }
.comment-field { margin-top: 14px; }
</style>
