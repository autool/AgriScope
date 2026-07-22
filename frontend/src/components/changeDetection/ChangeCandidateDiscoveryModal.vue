<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type { ChangeCandidateDiscoveryPayload } from '@/types/changeDetection'

const props = defineProps<{
  open: boolean
  runCode: string
  operatorCode: string | null
  saving: boolean
}>()

const emit = defineEmits<{
  close: []
  discover: [payload: ChangeCandidateDiscoveryPayload]
}>()

const differenceThresholdRef = ref<number>(0.18)
const minComponentPixelsRef = ref<number>(9)
const maxCandidatesRef = ref<number>(200)
const commentRef = ref<string>('')

const canSubmitComputed = computed<boolean>(() => Boolean(
  props.operatorCode
  && commentRef.value.trim()
  && differenceThresholdRef.value >= 0.01
  && differenceThresholdRef.value <= 1
  && minComponentPixelsRef.value >= 1
  && maxCandidatesRef.value >= 1,
))

const submit = (): void => {
  if (!canSubmitComputed.value || !props.operatorCode) return
  emit('discover', {
    difference_threshold: differenceThresholdRef.value,
    min_component_pixels: minComponentPixelsRef.value,
    max_candidates: maxCandidatesRef.value,
    operator_code: props.operatorCode,
    comment: commentRef.value.trim(),
  })
}

watch(
  () => props.open,
  (open) => {
    if (!open) return
    differenceThresholdRef.value = 0.18
    minComponentPixelsRef.value = 9
    maxCandidatesRef.value = 200
    commentRef.value = ''
  },
)
</script>

<template>
  <a-modal
    :open="open"
    :title="`自动发现变化候选 · ${runCode}`"
    :confirm-loading="saving"
    :ok-button-props="{ disabled: !canSubmitComputed }"
    width="620px"
    ok-text="运行并生成实体成果"
    @cancel="emit('close')"
    @ok="submit"
  >
    <a-alert
      type="warning"
      show-icon
      message="算法只发现显著变化，不推测业务地类"
      description="平台对共同网格影像执行确定性 RGB 绝对差分和连通域矢量化。结果统一标记为“未分类变化”，必须人工归入六类之一后才能确认。每个检测任务只能生成或导入一个冻结候选批次。"
    />
    <a-form layout="vertical" class="discovery-form">
      <div class="parameter-grid">
        <a-form-item label="RGB 平均差分阈值" required>
          <a-input-number
            v-model:value="differenceThresholdRef"
            :min="0.01"
            :max="1"
            :step="0.01"
            :precision="2"
          />
          <small>当前 {{ (differenceThresholdRef * 100).toFixed(0) }}%，越高越保守</small>
        </a-form-item>
        <a-form-item label="最小连通域像元" required>
          <a-input-number
            v-model:value="minComponentPixelsRef"
            :min="1"
            :max="100000"
            :precision="0"
          />
          <small>先过滤孤立噪声，再按冻结的 400㎡ 规则复核面积</small>
        </a-form-item>
        <a-form-item label="候选数量上限" required>
          <a-input-number
            v-model:value="maxCandidatesRef"
            :min="1"
            :max="500"
            :precision="0"
          />
          <small>超过上限将整次拒绝，不会静默截断</small>
        </a-form-item>
      </div>
      <a-form-item label="运行说明" required>
        <a-textarea
          v-model:value="commentRef"
          :rows="4"
          placeholder="说明阈值选择、影像质量、预期变化类型和后续人工复核安排"
        />
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<style scoped>
.discovery-form { margin-top: 14px; }
.parameter-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.parameter-grid :deep(.ant-input-number) { width: 100%; }
.parameter-grid small { display: block; margin-top: 4px; font-size: 9px; color: #7a8981; line-height: 1.5; }
</style>
