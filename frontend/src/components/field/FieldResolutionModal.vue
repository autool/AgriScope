<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type {
  FieldResolutionDecision,
  FieldResolutionPayload,
  FieldVerificationItem,
} from '@/types/workbench'

const props = defineProps<{
  open: boolean
  loading: boolean
  record: FieldVerificationItem | null
}>()

const emit = defineEmits<{
  cancel: []
  submit: [payload: Omit<FieldResolutionPayload, 'reviewer_code'>]
}>()

const decisionRef = ref<FieldResolutionDecision>('use_field')
const commentRef = ref<string>('')
const targetLandClassRef = ref<string | null>(null)
const targetCropTypeRef = ref<string | null>(null)

const hasMatchedPlotComputed = computed<boolean>(() => (
  Boolean(props.record?.matched_plot_code)
))
const canUseFieldComputed = computed<boolean>(() => {
  if (!hasMatchedPlotComputed.value || !props.record?.observed_land_class) {
    return false
  }
  return props.record.observed_land_class !== '耕地'
    || Boolean(props.record.observed_crop_type)
})
const isCompromiseComputed = computed<boolean>(() => (
  decisionRef.value === 'compromise'
))
const targetIsFarmlandComputed = computed<boolean>(() => (
  targetLandClassRef.value === '耕地'
))
const canSubmitComputed = computed<boolean>(() => {
  if (commentRef.value.trim().length < 2) return false
  if (!isCompromiseComputed.value) return true
  if (!targetLandClassRef.value) return false
  if (targetIsFarmlandComputed.value && !targetCropTypeRef.value) return false
  return targetIsFarmlandComputed.value || !targetCropTypeRef.value
})

const decisionDescriptions: Record<FieldResolutionDecision, string> = {
  use_field: '使用现场调查地类和作物修正当前匹配图斑。',
  keep_internal: '复核后确认内业边界与属性正确，不修改图斑。',
  compromise: '人工填写最终地类和作物，不由系统猜测折中结果。',
  reject_field: '认定外业定位或调查结论不适用于当前图斑。',
}

/**
 * 提交完整的外业处置表单。
 * Returns:
 *   void: 将用户填写的决策和依据交给父组件。
 */
const handleSubmit = (): void => {
  if (!canSubmitComputed.value) return
  emit('submit', {
    decision: decisionRef.value,
    comment: commentRef.value.trim(),
    target_land_class: isCompromiseComputed.value
      ? targetLandClassRef.value
      : null,
    target_crop_type: isCompromiseComputed.value
      ? targetCropTypeRef.value
      : null,
  })
}

watch(
  () => props.open,
  (open) => {
    if (!open) return
    decisionRef.value = canUseFieldComputed.value
      ? 'use_field'
      : hasMatchedPlotComputed.value ? 'keep_internal' : 'reject_field'
    commentRef.value = ''
    targetLandClassRef.value = null
    targetCropTypeRef.value = null
  },
)

watch(targetLandClassRef, (value) => {
  if (value !== '耕地') targetCropTypeRef.value = null
})
</script>

<template>
  <a-modal
    :open="open"
    title="外业疑点人工处置"
    :confirm-loading="loading"
    :ok-button-props="{ disabled: !canSubmitComputed }"
    ok-text="确认处置"
    cancel-text="取消"
    @ok="handleSubmit"
    @cancel="emit('cancel')"
  >
    <a-alert
      type="info"
      show-icon
      :message="record?.verification_code || '未选择外业记录'"
      :description="`匹配图斑：${record?.matched_plot_code || '未匹配'}；现场地类：${record?.observed_land_class || '未填写'}；现场作物：${record?.observed_crop_type || '无'}`"
    />
    <div class="resolution-form">
      <label>
        <span>处置决策</span>
        <a-select v-model:value="decisionRef">
          <a-select-option value="use_field" :disabled="!canUseFieldComputed">
            采用外业结论
          </a-select-option>
          <a-select-option value="keep_internal">保留内业成果</a-select-option>
          <a-select-option value="compromise" :disabled="!hasMatchedPlotComputed">
            人工折中方案
          </a-select-option>
          <a-select-option value="reject_field">驳回外业结论</a-select-option>
        </a-select>
      </label>
      <a-alert
        type="warning"
        show-icon
        :message="decisionDescriptions[decisionRef]"
      />
      <template v-if="isCompromiseComputed">
        <label>
          <span>最终地类</span>
          <a-select v-model:value="targetLandClassRef" placeholder="必须人工选择">
            <a-select-option value="耕地">耕地</a-select-option>
            <a-select-option value="园地">园地</a-select-option>
            <a-select-option value="林地">林地</a-select-option>
            <a-select-option value="草地">草地</a-select-option>
            <a-select-option value="水域">水域</a-select-option>
            <a-select-option value="建设用地">建设用地</a-select-option>
          </a-select>
        </label>
        <label v-if="targetIsFarmlandComputed">
          <span>最终作物</span>
          <a-select v-model:value="targetCropTypeRef" placeholder="耕地必须选择作物">
            <a-select-option value="水稻">水稻</a-select-option>
            <a-select-option value="玉米">玉米</a-select-option>
            <a-select-option value="小麦">小麦</a-select-option>
            <a-select-option value="大豆">大豆</a-select-option>
            <a-select-option value="马铃薯">马铃薯</a-select-option>
            <a-select-option value="杂粮">杂粮</a-select-option>
            <a-select-option value="其他">其他</a-select-option>
          </a-select>
        </label>
      </template>
      <label>
        <span>复核依据</span>
        <a-textarea
          v-model:value="commentRef"
          :rows="4"
          :maxlength="500"
          show-count
          placeholder="说明现场证据、影像判读、定位偏差和最终结论依据"
        />
      </label>
    </div>
  </a-modal>
</template>

<style scoped>
.resolution-form { display: grid; gap: 12px; margin-top: 14px; }
.resolution-form label { display: grid; gap: 5px; }
.resolution-form label > span { font-size: 12px; font-weight: 600; color: #3e4943; }
</style>
