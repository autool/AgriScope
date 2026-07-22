<script setup lang="ts">
import { computed, reactive, ref } from 'vue'

import type {
  SupervisionPlanCreatePayload,
  SupervisionSamplingMethod,
  SupervisionWorkArea,
} from '@/types/supervision'

const props = defineProps<{
  workAreas: SupervisionWorkArea[]
  operatorCode: string | null
  saving: boolean
}>()

const emit = defineEmits<{
  create: [payload: SupervisionPlanCreatePayload]
}>()

const openRef = ref<boolean>(false)
const formRef = reactive({
  planCode: '',
  planName: '',
  samplingMethod: 'systematic' as SupervisionSamplingMethod,
  sampleRatio: 5,
  minimumPerRegion: 3,
  regionCodes: [] as string[],
  plannedStartDate: '',
  plannedEndDate: '',
  comment: '',
})

const availableWorkAreasComputed = computed(() => (
  props.workAreas.filter((item) => item.plot_count > 0)
))

const expectedSampleCountComputed = computed<number>(() => (
  availableWorkAreasComputed.value
    .filter((item) => formRef.regionCodes.includes(item.region_code))
    .reduce((sum, item) => (
      sum + Math.min(
        item.plot_count,
        Math.max(
          formRef.minimumPerRegion,
          Math.ceil(item.plot_count * formRef.sampleRatio / 100),
        ),
      )
    ), 0)
))

const canSubmitComputed = computed<boolean>(() => Boolean(
  props.operatorCode
  && formRef.planCode.trim()
  && formRef.planName.trim()
  && formRef.regionCodes.length
  && formRef.plannedStartDate
  && formRef.plannedEndDate
  && formRef.comment.trim()
  && expectedSampleCountComputed.value <= 5000,
))

const open = (): void => {
  openRef.value = true
}

const close = (): void => {
  openRef.value = false
}

const submit = (): void => {
  if (!canSubmitComputed.value || !props.operatorCode) return
  emit('create', {
    plan_code: formRef.planCode.trim(),
    plan_name: formRef.planName.trim(),
    sampling_method: formRef.samplingMethod,
    sample_ratio: formRef.sampleRatio,
    minimum_per_region: formRef.minimumPerRegion,
    region_codes: formRef.regionCodes,
    planned_start_date: formRef.plannedStartDate,
    planned_end_date: formRef.plannedEndDate,
    operator_code: props.operatorCode,
    comment: formRef.comment.trim(),
  })
}

defineExpose({ open, close })
</script>

<template>
  <a-modal
    v-model:open="openRef"
    title="创建独立监理抽样计划"
    width="760px"
    :confirm-loading="saving"
    :ok-button-props="{ disabled: !canSubmitComputed }"
    ok-text="创建并固化样本"
    @ok="submit"
  >
    <a-alert
      type="info"
      show-icon
      message="样本直接来自当前任务真实图斑"
      description="平台按县区和计划编号执行可复现抽样，保存图斑版本、任务图斑总数和任务更新时间；任务范围变化后旧计划不能继续追加检查或生成报告。"
    />
    <a-form layout="vertical" class="plan-form">
      <div class="form-grid">
        <a-form-item label="计划编号" required>
          <a-input v-model:value="formRef.planCode" placeholder="例如 SV-2026-001" />
        </a-form-item>
        <a-form-item label="计划名称" required>
          <a-input v-model:value="formRef.planName" placeholder="例如 首轮独立监理抽样" />
        </a-form-item>
        <a-form-item label="抽样方法" required>
          <a-select v-model:value="formRef.samplingMethod">
            <a-select-option value="systematic">系统抽样</a-select-option>
            <a-select-option value="stratified_random">县区分层随机</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="抽样比例（%）" required>
          <a-input-number
            v-model:value="formRef.sampleRatio"
            :min="0.1"
            :max="100"
            :step="0.5"
            style="width: 100%"
          />
        </a-form-item>
        <a-form-item label="每县最少样本" required>
          <a-input-number
            v-model:value="formRef.minimumPerRegion"
            :min="1"
            :max="500"
            style="width: 100%"
          />
        </a-form-item>
        <a-form-item label="预计样本数">
          <a-input :value="`${expectedSampleCountComputed.toLocaleString()} / 5,000`" disabled />
        </a-form-item>
        <a-form-item label="计划开始日期" required>
          <a-date-picker v-model:value="formRef.plannedStartDate" value-format="YYYY-MM-DD" style="width: 100%" />
        </a-form-item>
        <a-form-item label="计划结束日期" required>
          <a-date-picker v-model:value="formRef.plannedEndDate" value-format="YYYY-MM-DD" style="width: 100%" />
        </a-form-item>
      </div>
      <a-form-item label="县区范围" required>
        <a-select
          v-model:value="formRef.regionCodes"
          mode="multiple"
          show-search
          :max-tag-count="8"
          placeholder="选择具有任务真实图斑的县区"
          option-filter-prop="label"
        >
          <a-select-option
            v-for="area in availableWorkAreasComputed"
            :key="area.region_code"
            :value="area.region_code"
            :label="`${area.city_name} / ${area.region_name} / ${area.plot_count} 图斑`"
          >
            {{ area.city_name }} / {{ area.region_name }} · {{ area.plot_count.toLocaleString() }} 图斑
          </a-select-option>
        </a-select>
      </a-form-item>
      <a-form-item label="抽样依据与说明" required>
        <a-textarea v-model:value="formRef.comment" :rows="3" placeholder="说明本轮监理目的、县区范围和抽样依据" />
      </a-form-item>
    </a-form>
    <a-alert
      v-if="expectedSampleCountComputed > 5000"
      type="error"
      show-icon
      message="预计样本超过单计划上限，请降低比例或减少县区"
    />
  </a-modal>
</template>

<style scoped>
.plan-form { margin-top: 14px; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 12px; }
@media (max-width: 720px) { .form-grid { grid-template-columns: 1fr; } }
</style>
