<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type {
  ChangeCandidate,
  ChangeCandidateReviewPayload,
  ChangeClass,
} from '@/types/changeDetection'
import { CHANGE_CLASS_LABELS } from '@/types/changeDetection'

const props = defineProps<{
  open: boolean
  candidate: ChangeCandidate | null
  reviewerCode: string | null
  saving: boolean
  canReview: boolean
}>()

const emit = defineEmits<{
  close: []
  review: [payload: ChangeCandidateReviewPayload]
}>()

const decisionRef = ref<'confirmed' | 'excluded'>('confirmed')
const changeClassRef = ref<ChangeClass | undefined>(undefined)
const exclusionReasonRef = ref<string>('')
const evidenceCommentRef = ref<string>('')
const reviewClassOptionsComputed = computed<Array<{
  value: ChangeClass
  label: string
}>>(() => (
  Object.entries(CHANGE_CLASS_LABELS)
    .filter(([value]) => value !== 'unclassified')
    .map(([value, label]) => ({ value: value as ChangeClass, label }))
))

const canSubmitComputed = computed<boolean>(() => Boolean(
  props.canReview
  && props.reviewerCode
  && props.candidate
  && evidenceCommentRef.value.trim()
  && (decisionRef.value === 'excluded' || changeClassRef.value)
  && (decisionRef.value === 'confirmed' || exclusionReasonRef.value.trim()),
))

const submit = (): void => {
  if (!canSubmitComputed.value || !props.reviewerCode) return
  emit('review', {
    decision: decisionRef.value,
    change_class: changeClassRef.value,
    exclusion_reason: decisionRef.value === 'excluded'
      ? exclusionReasonRef.value.trim()
      : null,
    evidence_comment: evidenceCommentRef.value.trim(),
    reviewer_code: props.reviewerCode,
  })
}

watch(
  () => [props.open, props.candidate] as const,
  ([open, candidate]) => {
    if (!open || !candidate) return
    decisionRef.value = candidate.status === 'excluded' ? 'excluded' : 'confirmed'
    changeClassRef.value = candidate.change_class === 'unclassified'
      ? undefined
      : candidate.change_class
    exclusionReasonRef.value = candidate.exclusion_reason || ''
    evidenceCommentRef.value = candidate.review_comment || ''
  },
)
</script>

<template>
  <a-drawer
    :open="open"
    title="变化候选人工判读"
    width="460"
    @close="emit('close')"
  >
    <template v-if="candidate">
      <section class="candidate-summary">
        <header>
          <span><strong>{{ candidate.candidate_code }}</strong><small>{{ candidate.source_name }} · {{ candidate.source_version }}</small></span>
          <a-tag :color="candidate.status === 'confirmed' ? 'green' : candidate.status === 'excluded' ? 'default' : 'orange'">
            {{ candidate.status === 'confirmed' ? '已确认' : candidate.status === 'excluded' ? '已排除' : '待判读' }}
          </a-tag>
        </header>
        <dl>
          <div><dt>模型类别</dt><dd>{{ CHANGE_CLASS_LABELS[candidate.change_class] }}</dd></div>
          <div><dt>置信度</dt><dd>{{ (candidate.confidence * 100).toFixed(1) }}%</dd></div>
          <div><dt>面积</dt><dd>{{ candidate.area_ha.toFixed(4) }} ha</dd></div>
          <div><dt>来源要素</dt><dd>{{ candidate.source_feature_id }}</dd></div>
        </dl>
        <a :href="candidate.evidence_uri" target="_blank" rel="noreferrer">查看来源证据</a>
      </section>

      <a-divider>人工结论</a-divider>
      <a-form layout="vertical">
        <a-form-item label="判读结论" required>
          <a-radio-group v-model:value="decisionRef" :disabled="!canReview">
            <a-radio-button value="confirmed">确认变化</a-radio-button>
            <a-radio-button value="excluded">排除候选</a-radio-button>
          </a-radio-group>
        </a-form-item>
        <a-form-item label="最终变化类别" required>
          <a-select
            v-model:value="changeClassRef"
            :disabled="!canReview"
            placeholder="必须人工选择六类变化之一"
          >
            <a-select-option
              v-for="option in reviewClassOptionsComputed"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item v-if="decisionRef === 'excluded'" label="排除原因" required>
          <a-textarea v-model:value="exclusionReasonRef" :rows="3" :disabled="!canReview" />
        </a-form-item>
        <a-form-item label="影像/调查证据说明" required>
          <a-textarea
            v-model:value="evidenceCommentRef"
            :rows="4"
            :disabled="!canReview"
            placeholder="说明前后时相差异、参考底图、外业或其他证据"
          />
        </a-form-item>
        <a-button
          type="primary"
          block
          :loading="saving"
          :disabled="!canSubmitComputed"
          @click="submit"
        >
          保存判读并追加审计历史
        </a-button>
      </a-form>

      <a-divider>不可变判读历史</a-divider>
      <a-empty v-if="!candidate.history.length" description="尚无判读事件" />
      <a-timeline v-else>
        <a-timeline-item v-for="event in candidate.history" :key="`${event.created_at}-${event.event_type}`">
          <strong>{{ event.event_type === 'candidate_imported' ? '候选导入' : '人工判读' }}</strong>
          <small>{{ event.operator }} · {{ new Date(event.created_at).toLocaleString() }}</small>
          <p>{{ event.comment }}</p>
        </a-timeline-item>
      </a-timeline>
    </template>
  </a-drawer>
</template>

<style scoped>
.candidate-summary { padding: 11px; background: #f5f8f6; border: 1px solid #dde6e0; border-radius: 7px; }
.candidate-summary header { display: flex; justify-content: space-between; align-items: flex-start; }
.candidate-summary header span { display: flex; flex-direction: column; }
.candidate-summary header small { color: #718077; }
.candidate-summary dl { display: grid; grid-template-columns: 1fr 1fr; gap: 7px; }
.candidate-summary dl div { padding: 6px; background: #fff; border-radius: 4px; }
.candidate-summary dt, .ant-timeline small { display: block; font-size: 10px; color: #7b8982; }
.candidate-summary dd { margin: 2px 0 0; font-size: 12px; font-weight: 600; }
.ant-timeline strong, .ant-timeline small { display: block; }
.ant-timeline p { margin: 4px 0 0; font-size: 11px; color: #58675f; }
</style>
