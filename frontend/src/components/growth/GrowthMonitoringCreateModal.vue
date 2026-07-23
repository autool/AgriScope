<script setup lang="ts">
import { computed, reactive, watch } from 'vue'

import type {
  GrowthMonitoringCreatePayload,
  GrowthMonitoringSource,
} from '@/types/growthMonitoring'

interface Props {
  open: boolean
  loading: boolean
  sources: GrowthMonitoringSource[]
  maxOutputPixels: number
}

const props = defineProps<Props>()
const emit = defineEmits<{
  cancel: []
  submit: [payload: Omit<GrowthMonitoringCreatePayload, 'operator_code'>]
}>()

const buildRunCode = (): string => {
  const timestamp = new Date().toISOString().replace(/[-:TZ.]/g, '').slice(0, 14)
  return `GROWTH-${timestamp}`
}

const form = reactive<Omit<GrowthMonitoringCreatePayload, 'operator_code'>>({
  run_code: buildRunCode(),
  run_name: '多时相 NDVI 作物长势监测',
  baseline_asset_code: '',
  current_asset_code: '',
  poor_delta_threshold: -0.05,
  good_delta_threshold: 0.05,
  minimum_zone_area_ha: 1,
  minimum_spatial_coverage_ratio: 0.8,
  minimum_valid_pixel_ratio: 0.8,
  comment: '',
})

const sourceByCodeComputed = computed<Map<string, GrowthMonitoringSource>>(() => (
  new Map(props.sources.map((source) => [source.asset_code, source]))
))
const baselineComputed = computed(() => (
  sourceByCodeComputed.value.get(form.baseline_asset_code) || null
))
const currentComputed = computed(() => (
  sourceByCodeComputed.value.get(form.current_asset_code) || null
))
const timeOrderValidComputed = computed<boolean>(() => (
  Boolean(
    baselineComputed.value
    && currentComputed.value
    && new Date(baselineComputed.value.acquired_at).getTime()
      < new Date(currentComputed.value.acquired_at).getTime(),
  )
))
const canSubmitComputed = computed<boolean>(() => (
  form.run_code.trim().length > 0
  && form.run_name.trim().length > 0
  && form.baseline_asset_code !== form.current_asset_code
  && timeOrderValidComputed.value
  && form.poor_delta_threshold < 0
  && form.good_delta_threshold > 0
  && form.minimum_zone_area_ha > 0
  && form.minimum_spatial_coverage_ratio > 0
  && form.minimum_spatial_coverage_ratio <= 1
  && form.minimum_valid_pixel_ratio > 0
  && form.minimum_valid_pixel_ratio <= 1
  && form.comment.trim().length >= 10
))

watch(
  () => props.open,
  (open) => {
    if (!open) return
    form.run_code = buildRunCode()
    const chronological = [...props.sources].sort(
      (left, right) => (
        new Date(left.acquired_at).getTime() - new Date(right.acquired_at).getTime()
      ),
    )
    form.baseline_asset_code = chronological[0]?.asset_code || ''
    form.current_asset_code = chronological.at(-1)?.asset_code || ''
  },
)

const submit = (): void => {
  if (!canSubmitComputed.value) return
  emit('submit', {
    ...form,
    run_code: form.run_code.trim(),
    run_name: form.run_name.trim(),
    comment: form.comment.trim(),
  })
}
</script>

<template>
  <a-modal
    :open="open"
    title="生成多时相 NDVI 长势监测"
    width="720px"
    :confirm-loading="loading"
    :ok-button-props="{ disabled: !canSubmitComputed }"
    ok-text="服务端生成实体成果"
    cancel-text="取消"
    @cancel="emit('cancel')"
    @ok="submit"
  >
    <a-alert
      type="info"
      show-icon
      message="只使用已完成并通过大小、SHA-256 复核的 band_products 实体"
      :description="`服务端最多处理 ${maxOutputPixels.toLocaleString()} 像元，并将两期 NDVI 限定到当前任务真实耕地图斑范围。`"
    />
    <div class="form-grid">
      <label><span>任务编号</span><a-input v-model:value="form.run_code" /></label>
      <label><span>任务名称</span><a-input v-model:value="form.run_name" /></label>
      <label>
        <span>基准期影像</span>
        <a-select v-model:value="form.baseline_asset_code">
          <a-select-option
            v-for="source in sources"
            :key="source.asset_code"
            :value="source.asset_code"
          >
            {{ source.acquired_at.slice(0, 10) }} · {{ source.asset_name }}
          </a-select-option>
        </a-select>
      </label>
      <label>
        <span>监测期影像</span>
        <a-select v-model:value="form.current_asset_code">
          <a-select-option
            v-for="source in sources"
            :key="source.asset_code"
            :value="source.asset_code"
          >
            {{ source.acquired_at.slice(0, 10) }} · {{ source.asset_name }}
          </a-select-option>
        </a-select>
      </label>
      <label><span>转差阈值 ΔNDVI ≤</span><a-input-number
        v-model:value="form.poor_delta_threshold"
        :min="-1"
        :max="-0.001"
        :step="0.01"
      /></label>
      <label><span>转好阈值 ΔNDVI ≥</span><a-input-number
        v-model:value="form.good_delta_threshold"
        :min="0.001"
        :max="1"
        :step="0.01"
      /></label>
      <label><span>最小异常区（公顷）</span><a-input-number
        v-model:value="form.minimum_zone_area_ha"
        :min="0.01"
        :max="500"
        :step="0.1"
      /></label>
      <label><span>任务耕地空间覆盖门槛</span><a-input-number
        v-model:value="form.minimum_spatial_coverage_ratio"
        :min="0.01"
        :max="1"
        :step="0.05"
      /></label>
      <label><span>共同范围有效像元门槛</span><a-input-number
        v-model:value="form.minimum_valid_pixel_ratio"
        :min="0.1"
        :max="1"
        :step="0.05"
      /></label>
    </div>
    <a-alert
      v-if="form.baseline_asset_code && form.current_asset_code && !timeOrderValidComputed"
      type="error"
      show-icon
      message="基准期采集时间必须早于监测期"
    />
    <a-alert
      type="warning"
      show-icon
      message="空间覆盖与像元有效率是两个独立质量门禁"
      description="空间覆盖率以完整任务耕地面积为分母；有效像元率只评价两期影像共同足迹覆盖范围内的可用 NDVI 像元。降低任一门槛都会写入成果清单。"
    />
    <label class="comment-field">
      <span>生成依据</span>
      <a-textarea
        v-model:value="form.comment"
        :rows="3"
        :maxlength="500"
        placeholder="说明监测时段、作物生育期、阈值依据和成果用途，至少 10 个字"
      />
    </label>
  </a-modal>
</template>

<style scoped>
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 16px 0; }
label { display: grid; gap: 6px; }
label > span { font-size: 12px; color: #42544b; }
.comment-field { margin-top: 12px; }
:deep(.ant-input-number) { width: 100%; }
</style>
