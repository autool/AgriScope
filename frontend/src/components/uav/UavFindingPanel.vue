<script setup lang="ts">
import { message } from 'ant-design-vue'
import { computed, ref, watch } from 'vue'

import type { UavArtifact, UavFinding, UavFindingCreatePayload, UavMission } from '@/types/uav'

const props = defineProps<{
  mission: UavMission | null
  artifacts: UavArtifact[]
  findings: UavFinding[]
  pickedCoordinate: { lon: number; lat: number } | null
  canOperate: boolean
  canReview: boolean
  loading: boolean
}>()

const emit = defineEmits<{
  'create-finding': [missionCode: string, payload: Omit<UavFindingCreatePayload, 'operator_code'>]
  'review-finding': [missionCode: string, findingCode: string, decision: 'confirm' | 'dismiss', comment: string]
}>()

const findingModalOpenRef = ref<boolean>(false)
const reviewModalOpenRef = ref<boolean>(false)
const targetFindingRef = ref<UavFinding | null>(null)
const reviewDecisionRef = ref<'confirm' | 'dismiss'>('confirm')
const reviewCommentRef = ref<string>('')
const findingCodeRef = ref<string>('')
const artifactCodeRef = ref<string>('')
const findingTypeRef = ref<string>('')
const severityRef = ref<'minor' | 'major' | 'critical'>('major')
const longitudeRef = ref<number | null>(null)
const latitudeRef = ref<number | null>(null)
const plotCodeRef = ref<string>('')
const descriptionRef = ref<string>('')

watch(() => props.pickedCoordinate, (coordinate) => {
  if (!coordinate) return
  longitudeRef.value = coordinate.lon
  latitudeRef.value = coordinate.lat
}, { deep: true, immediate: true })

const missionArtifactsComputed = computed(() => (
  props.mission
    ? props.artifacts.filter(item => item.mission_code === props.mission?.mission_code)
    : []
))
const missionFindingsComputed = computed(() => (
  props.mission
    ? props.findings.filter(item => item.mission_code === props.mission?.mission_code)
    : []
))

const submitFinding = (): void => {
  if (
    !props.mission || !findingCodeRef.value || !artifactCodeRef.value
    || !findingTypeRef.value || longitudeRef.value === null || latitudeRef.value === null
    || descriptionRef.value.trim().length < 4
  ) {
    message.warning('请完整填写疑点编号、证据成果、坐标、类型和说明')
    return
  }
  emit('create-finding', props.mission.mission_code, {
    finding_code: findingCodeRef.value.trim(),
    artifact_code: artifactCodeRef.value,
    finding_type: findingTypeRef.value.trim(),
    severity: severityRef.value,
    longitude: longitudeRef.value,
    latitude: latitudeRef.value,
    ...(plotCodeRef.value.trim() ? { plot_code: plotCodeRef.value.trim() } : {}),
    description: descriptionRef.value.trim(),
  })
  findingModalOpenRef.value = false
}

const openReview = (finding: UavFinding, decision: 'confirm' | 'dismiss'): void => {
  targetFindingRef.value = finding
  reviewDecisionRef.value = decision
  reviewCommentRef.value = ''
  reviewModalOpenRef.value = true
}

const submitReview = (): void => {
  if (!props.mission || !targetFindingRef.value || reviewCommentRef.value.trim().length < 4) {
    message.warning('请填写人工复核依据')
    return
  }
  emit(
    'review-finding',
    props.mission.mission_code,
    targetFindingRef.value.finding_code,
    reviewDecisionRef.value,
    reviewCommentRef.value.trim(),
  )
  reviewModalOpenRef.value = false
}
</script>

<template>
  <section class="finding-panel">
    <header>
      <div><small>SPATIAL FINDINGS</small><h3>空间疑点与人工复核</h3></div>
      <a-space size="small">
        <a-tag v-if="pickedCoordinate" color="purple">地图坐标已拾取</a-tag>
        <a-button
          size="small"
          type="primary"
          :disabled="!mission || !canOperate || !['captured', 'processed'].includes(mission.status) || !missionArtifactsComputed.length"
          @click="findingModalOpenRef = true"
        >
          登记疑点
        </a-button>
      </a-space>
    </header>
    <a-alert
      v-if="mission"
      type="info"
      show-icon
      :message="`${mission.mission_code} · 疑点坐标必须位于飞行范围，关联图斑必须属于 ${mission.task_code}`"
    />
    <a-empty v-else description="选择无人机任务后查看疑点和复核记录" />
    <div v-if="mission" class="finding-list">
      <article v-for="finding in missionFindingsComputed" :key="finding.finding_code">
        <div class="heading"><span><strong>{{ finding.finding_type }}</strong><em>{{ finding.finding_code }} · {{ finding.artifact_code }}</em></span><a-tag :color="finding.status === 'confirmed' ? 'red' : finding.status === 'dismissed' ? 'default' : 'orange'">{{ finding.status }}</a-tag></div>
        <p>{{ finding.description }}</p>
        <div class="meta"><span>{{ finding.longitude.toFixed(6) }}, {{ finding.latitude.toFixed(6) }}</span><span>{{ finding.plot_code || '未关联图斑' }} · {{ finding.severity }}</span></div>
        <footer v-if="finding.status === 'pending_review'">
          <a-button size="small" :disabled="!canReview" @click="openReview(finding, 'dismiss')">排除</a-button>
          <a-button
            size="small"
            type="primary"
            danger
            :disabled="!canReview"
            @click="openReview(finding, 'confirm')"
          >
            确认疑点
          </a-button>
        </footer>
        <footer v-else><span>{{ finding.reviewed_by || '--' }} · {{ finding.review_comment || '--' }}</span></footer>
      </article>
      <a-empty v-if="!missionFindingsComputed.length" description="当前任务没有无人机空间疑点" />
    </div>

    <a-modal
      v-model:open="findingModalOpenRef"
      title="登记无人机空间疑点"
      :confirm-loading="loading"
      @ok="submitFinding"
    >
      <div class="form-grid">
        <label><span>疑点编号</span><a-input v-model:value="findingCodeRef" /></label>
        <label><span>证据成果</span><a-select v-model:value="artifactCodeRef" :options="missionArtifactsComputed.map(item => ({ value: item.artifact_code, label: `${item.artifact_code} · ${item.artifact_type}` }))" /></label>
        <label><span>疑点类型</span><a-input v-model:value="findingTypeRef" /></label>
        <label><span>严重度</span><a-select v-model:value="severityRef" :options="[{ value: 'minor', label: '轻微' }, { value: 'major', label: '严重' }, { value: 'critical', label: '紧急' }]" /></label>
        <label><span>WGS84 经度</span><a-input-number v-model:value="longitudeRef" :precision="7" /></label>
        <label><span>WGS84 纬度</span><a-input-number v-model:value="latitudeRef" :precision="7" /></label>
        <label class="wide"><span>关联任务图斑（可选）</span><a-input v-model:value="plotCodeRef" /></label>
        <label class="wide"><span>疑点说明</span><a-textarea v-model:value="descriptionRef" :rows="4" /></label>
      </div>
    </a-modal>

    <a-modal
      v-model:open="reviewModalOpenRef"
      :title="reviewDecisionRef === 'confirm' ? '确认无人机疑点' : '排除无人机疑点'"
      :confirm-loading="loading"
      @ok="submitReview"
    >
      <label><span>人工判读、外业或影像证据依据</span><a-textarea v-model:value="reviewCommentRef" :rows="4" /></label>
    </a-modal>
  </section>
</template>

<style scoped>
.finding-panel { display: flex; flex-direction: column; min-height: 0; padding: 12px; overflow: hidden; background: #fff; border: 1px solid #dfe5e2; border-radius: 8px; }
header, .heading, .meta, footer { display: flex; align-items: center; justify-content: space-between; gap: 10px; } header { margin-bottom: 8px; } small { font-size: 8px; color: #718078; letter-spacing: 1px; } h3 { margin: 2px 0 0; font-size: 15px; color: #20352c; }
.finding-list { display: flex; flex: 1; min-height: 0; flex-direction: column; gap: 6px; padding-top: 9px; overflow: auto; } article { padding: 8px; border: 1px solid #e4dfda; border-left: 3px solid #d78b54; border-radius: 6px; } .heading span { display: flex; min-width: 0; flex-direction: column; } strong { font-size: 11px; color: #294137; } em { overflow: hidden; font-size: 8px; font-style: normal; color: #7c8a83; text-overflow: ellipsis; white-space: nowrap; } p { margin: 6px 0; font-size: 9px; color: #68776f; } .meta, footer { font-size: 8px; color: #89958f; } footer { justify-content: flex-end; margin-top: 7px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; } label { display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: #56665e; } label.wide { grid-column: 1 / -1; } label :deep(.ant-input-number), label :deep(.ant-select) { width: 100%; }
</style>
