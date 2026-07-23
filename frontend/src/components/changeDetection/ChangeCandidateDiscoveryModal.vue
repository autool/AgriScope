<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type {
  ChangeCandidateDiscoveryPayload,
  ChangeDiscoveryAlgorithm,
  ChangeDiscoveryAlgorithmCode,
} from '@/types/changeDetection'

const props = defineProps<{
  open: boolean
  runCode: string
  algorithms: ChangeDiscoveryAlgorithm[]
  operatorCode: string | null
  saving: boolean
}>()

const emit = defineEmits<{
  close: []
  discover: [payload: ChangeCandidateDiscoveryPayload]
}>()

const algorithmCodeRef = ref<ChangeDiscoveryAlgorithmCode>('rgb_absolute_difference')
const differenceThresholdRef = ref<number>(0.18)
const minComponentPixelsRef = ref<number>(9)
const maxCandidatesRef = ref<number>(200)
const commentRef = ref<string>('')

const selectedAlgorithmComputed = computed<ChangeDiscoveryAlgorithm | null>(() => (
  props.algorithms.find((item) => item.code === algorithmCodeRef.value) || null
))

const canSubmitComputed = computed<boolean>(() => Boolean(
  props.operatorCode
  && selectedAlgorithmComputed.value
  && commentRef.value.trim()
  && differenceThresholdRef.value >= (
    selectedAlgorithmComputed.value?.threshold_min ?? 0.01
  )
  && differenceThresholdRef.value <= (
    selectedAlgorithmComputed.value?.threshold_max ?? 1
  )
  && minComponentPixelsRef.value >= 1
  && maxCandidatesRef.value >= 1,
))

const submit = (): void => {
  if (!canSubmitComputed.value || !props.operatorCode) return
  emit('discover', {
    algorithm_code: algorithmCodeRef.value,
    difference_threshold: differenceThresholdRef.value,
    min_component_pixels: minComponentPixelsRef.value,
    max_candidates: maxCandidatesRef.value,
    operator_code: props.operatorCode,
    comment: commentRef.value.trim(),
  })
}

const selectAlgorithm = (algorithm: ChangeDiscoveryAlgorithm): void => {
  algorithmCodeRef.value = algorithm.code
  differenceThresholdRef.value = algorithm.default_threshold
}

watch(
  () => props.open,
  (open) => {
    if (!open) return
    const defaultAlgorithm = props.algorithms.find(
      (item) => item.code === 'rgb_absolute_difference',
    ) || props.algorithms[0]
    if (defaultAlgorithm) selectAlgorithm(defaultAlgorithm)
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
    cancel-text="取消"
    @cancel="emit('close')"
    @ok="submit"
  >
    <a-alert
      type="warning"
      show-icon
      message="算法只发现显著变化，不推测业务地类"
      description="平台只读取两期实体栅格生成的同一公共网格预览。所选算法、版本、公式、阈值、双期预览 SHA-256 和成果 GeoJSON SHA-256 会一并留痕；结果仍统一标记为“未分类变化”，必须人工归入六类之一后才能确认。"
    />
    <a-form layout="vertical" class="discovery-form">
      <a-form-item label="候选发现算法" required>
        <div v-if="algorithms.length" class="algorithm-grid">
          <button
            v-for="algorithm in algorithms"
            :key="algorithm.code"
            type="button"
            :class="{ active: algorithm.code === algorithmCodeRef }"
            @click="selectAlgorithm(algorithm)"
          >
            <span><strong>{{ algorithm.name }}</strong><a-tag>v{{ algorithm.version }}</a-tag></span>
            <p>{{ algorithm.description }}</p>
            <code>{{ algorithm.score_formula }}</code>
          </button>
        </div>
        <a-empty v-else :image="false" description="服务端未注册可执行候选发现算法" />
      </a-form-item>
      <div class="parameter-grid">
        <a-form-item label="变化分数阈值" required>
          <a-input-number
            v-model:value="differenceThresholdRef"
            :min="selectedAlgorithmComputed?.threshold_min || 0.01"
            :max="selectedAlgorithmComputed?.threshold_max || 1"
            :step="0.01"
            :precision="2"
          />
          <small>当前 {{ (differenceThresholdRef * 100).toFixed(0) }}%，按所选算法变化分数判定</small>
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
.algorithm-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.algorithm-grid button { padding: 10px; text-align: left; background: #fafbfa; border: 1px solid #dfe6e2; border-radius: 6px; cursor: pointer; }
.algorithm-grid button.active { background: #f1f8f4; border-color: #4c956d; box-shadow: inset 3px 0 #4c956d; }
.algorithm-grid button > span { display: flex; align-items: center; justify-content: space-between; }
.algorithm-grid strong { font-size: 10px; color: #2f4037; }
.algorithm-grid p { min-height: 30px; margin: 6px 0; font-size: 8px; color: #68776f; line-height: 1.5; }
.algorithm-grid code { display: block; overflow: hidden; font-size: 7px; color: #4c6f5c; text-overflow: ellipsis; white-space: nowrap; }
.parameter-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.parameter-grid :deep(.ant-input-number) { width: 100%; }
.parameter-grid small { display: block; margin-top: 4px; font-size: 9px; color: #7a8981; line-height: 1.5; }
</style>
