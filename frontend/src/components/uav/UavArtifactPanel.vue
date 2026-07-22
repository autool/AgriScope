<script setup lang="ts">
import { message } from 'ant-design-vue'
import type { UploadProps } from 'ant-design-vue'
import { computed, ref, shallowRef } from 'vue'

import type {
  ArtifactUploadMetadata,
  UavArtifact,
  UavArtifactType,
  UavMission,
  UavMissionAction,
} from '@/types/uav'

const props = defineProps<{
  mission: UavMission | null
  artifacts: UavArtifact[]
  canOperate: boolean
  canReview: boolean
  canDownload: boolean
  loading: boolean
}>()

const emit = defineEmits<{
  'upload-artifact': [missionCode: string, file: File, metadata: ArtifactUploadMetadata]
  'transition': [missionCode: string, action: UavMissionAction, comment: string, actualTime: string | null]
  'download': [artifactCode: string, filename: string]
}>()

const uploadModalOpenRef = ref<boolean>(false)
const transitionModalOpenRef = ref<boolean>(false)
const selectedFileRef = shallowRef<File | null>(null)
const artifactCodeRef = ref<string>('')
const artifactTypeRef = ref<UavArtifactType>('raw_imagery')
const capturedAtRef = ref<string>('')
const sourceNameRef = ref<string>('')
const sourceVersionRef = ref<string>('')
const metadataJsonRef = ref<string>('{}')
const transitionActionRef = ref<UavMissionAction>('start')
const transitionCommentRef = ref<string>('')
const actualTimeRef = ref<string>('')

const missionArtifactsComputed = computed(() => (
  props.mission
    ? props.artifacts.filter(item => item.mission_code === props.mission?.mission_code)
    : []
))

const nextActionsComputed = computed<Array<{ action: UavMissionAction, label: string, review?: boolean }>>(() => {
  if (!props.mission) return []
  const actions: Record<UavMission['status'], Array<{ action: UavMissionAction, label: string, review?: boolean }>> = {
    planned: [{ action: 'start', label: '开始飞行' }, { action: 'cancel', label: '取消任务' }],
    in_progress: [{ action: 'complete_capture', label: '完成采集' }, { action: 'cancel', label: '取消任务' }],
    captured: [{ action: 'complete_processing', label: '完成处理' }, { action: 'cancel', label: '取消任务' }],
    processed: [{ action: 'complete_review', label: '完成审核', review: true }, { action: 'cancel', label: '取消任务' }],
    reviewed: [],
    cancelled: [],
  }
  return actions[props.mission.status]
})

const beforeUpload: UploadProps['beforeUpload'] = (file) => {
  selectedFileRef.value = file
  return false
}

const submitUpload = (): void => {
  if (
    !props.mission || !selectedFileRef.value || !artifactCodeRef.value
    || !sourceNameRef.value || !sourceVersionRef.value
  ) {
    message.warning('请选择实体文件并填写成果编号、来源和版本')
    return
  }
  let metadata: Record<string, unknown>
  try {
    metadata = JSON.parse(metadataJsonRef.value) as Record<string, unknown>
  } catch {
    message.warning('成果扩展元数据必须是合法 JSON 对象')
    return
  }
  emit('upload-artifact', props.mission.mission_code, selectedFileRef.value, {
    artifactCode: artifactCodeRef.value.trim(),
    artifactType: artifactTypeRef.value,
    capturedAt: capturedAtRef.value.trim() || null,
    sourceName: sourceNameRef.value.trim(),
    sourceVersion: sourceVersionRef.value.trim(),
    metadata,
  })
  uploadModalOpenRef.value = false
}

const openTransition = (action: UavMissionAction): void => {
  transitionActionRef.value = action
  transitionCommentRef.value = ''
  actualTimeRef.value = ''
  transitionModalOpenRef.value = true
}

const submitTransition = (): void => {
  if (!props.mission || transitionCommentRef.value.trim().length < 2) {
    message.warning('请填写任务状态变更依据')
    return
  }
  emit(
    'transition',
    props.mission.mission_code,
    transitionActionRef.value,
    transitionCommentRef.value.trim(),
    actualTimeRef.value.trim() || null,
  )
  transitionModalOpenRef.value = false
}
</script>

<template>
  <section class="artifact-panel">
    <header>
      <div><small>PHYSICAL EVIDENCE</small><h3>任务实体成果与状态门禁</h3></div>
      <a-button
        size="small"
        type="primary"
        :disabled="!mission || !canOperate || ['reviewed', 'cancelled'].includes(mission.status)"
        @click="uploadModalOpenRef = true"
      >
        上传实体成果
      </a-button>
    </header>
    <div v-if="mission" class="mission-summary">
      <div><span><strong>{{ mission.mission_name }}</strong><em>{{ mission.mission_code }} · {{ mission.aircraft_name }}</em></span><a-tag>{{ mission.status }}</a-tag></div>
      <p>{{ mission.district_name }} · {{ mission.planned_area_ha.toFixed(2) }} ha · 飞手 {{ mission.pilot_name }} / {{ mission.pilot_license_number }}</p>
      <p>{{ mission.altitude_m }} m · 目标 {{ mission.expected_resolution_cm }} cm · 重叠 {{ mission.forward_overlap_percent }}% / {{ mission.side_overlap_percent }}%</p>
      <a-space wrap>
        <a-button
          v-for="item in nextActionsComputed"
          :key="item.action"
          size="small"
          :danger="item.action === 'cancel'"
          :type="item.action === 'cancel' ? 'default' : 'primary'"
          :disabled="item.review ? !canReview : !canOperate"
          @click="openTransition(item.action)"
        >
          {{ item.label }}
        </a-button>
      </a-space>
    </div>
    <a-empty v-else description="从左侧选择无人机任务后管理实体成果" />

    <div v-if="mission" class="artifact-list">
      <article v-for="artifact in missionArtifactsComputed" :key="artifact.artifact_code">
        <div><span><strong>{{ artifact.artifact_code }}</strong><em>{{ artifact.artifact_type }} · {{ artifact.original_filename }}</em></span><a-tag color="green">{{ artifact.verification_status }}</a-tag></div>
        <p>{{ (artifact.file_size_bytes / 1024 / 1024).toFixed(2) }} MB · SHA {{ artifact.checksum_sha256.slice(0, 12) }}…</p>
        <p v-if="artifact.crs">{{ artifact.crs }} · {{ artifact.resolution_cm }} cm · {{ artifact.raster_width }}×{{ artifact.raster_height }}</p>
        <a-button
          size="small"
          type="link"
          :disabled="!canDownload"
          @click="emit('download', artifact.artifact_code, artifact.original_filename)"
        >
          校验并下载
        </a-button>
      </article>
      <a-empty v-if="!missionArtifactsComputed.length" description="尚未上传原始影像、航迹或正射实体" />
    </div>

    <a-modal
      v-model:open="uploadModalOpenRef"
      title="上传无人机任务实体成果"
      :confirm-loading="loading"
      @ok="submitUpload"
    >
      <div class="form-grid">
        <label><span>成果编号</span><a-input v-model:value="artifactCodeRef" /></label>
        <label><span>成果类型</span><a-select
          v-model:value="artifactTypeRef"
          :options="[
            { value: 'raw_imagery', label: '原始影像' }, { value: 'flight_log', label: '航迹日志' }, { value: 'photo', label: '证据照片' }, { value: 'video', label: '证据视频' }, { value: 'orthomosaic', label: '正射成果' }, { value: 'dem', label: 'DEM' }, { value: 'report', label: '任务报告' },
          ]"
        /></label>
        <label><span>采集时间（可选）</span><a-input v-model:value="capturedAtRef" placeholder="ISO 8601，必须含时区" /></label>
        <label><span>来源版本</span><a-input v-model:value="sourceVersionRef" /></label>
        <label class="wide"><span>来源名称</span><a-input v-model:value="sourceNameRef" /></label>
        <label class="wide"><span>扩展元数据 JSON</span><a-textarea v-model:value="metadataJsonRef" :rows="3" /></label>
        <label class="wide"><span>实体文件</span><a-upload :before-upload="beforeUpload" :max-count="1"><a-button>选择文件</a-button></a-upload></label>
      </div>
    </a-modal>

    <a-modal
      v-model:open="transitionModalOpenRef"
      title="执行无人机任务状态动作"
      :confirm-loading="loading"
      @ok="submitTransition"
    >
      <a-alert type="info" show-icon :message="`动作：${transitionActionRef}`" />
      <div class="form-grid transition-form">
        <label class="wide"><span>状态变更依据</span><a-textarea v-model:value="transitionCommentRef" :rows="4" /></label>
        <label class="wide"><span>实际时间（可选）</span><a-input v-model:value="actualTimeRef" placeholder="ISO 8601，留空使用服务器当前时间" /></label>
      </div>
    </a-modal>
  </section>
</template>

<style scoped>
.artifact-panel { display: flex; flex-direction: column; min-height: 0; padding: 12px; overflow: hidden; background: #fff; border: 1px solid #dfe5e2; border-radius: 8px; }
header, .mission-summary > div, .artifact-list article > div { display: flex; align-items: center; justify-content: space-between; gap: 10px; } header { margin-bottom: 8px; } small { font-size: 8px; color: #718078; letter-spacing: 1px; } h3 { margin: 2px 0 0; font-size: 15px; color: #20352c; }
.mission-summary { padding: 9px; background: #f0f7f3; border: 1px solid #d7e8de; border-radius: 7px; } .mission-summary span, .artifact-list span { display: flex; min-width: 0; flex-direction: column; } strong { font-size: 11px; color: #294137; } em { overflow: hidden; font-size: 8px; font-style: normal; color: #7c8a83; text-overflow: ellipsis; white-space: nowrap; } p { margin: 5px 0; font-size: 8px; color: #7c8a83; }
.artifact-list { display: flex; flex: 1; min-height: 0; flex-direction: column; gap: 6px; padding-top: 9px; overflow: auto; } .artifact-list article { padding: 8px; border: 1px solid #e1e7e4; border-radius: 6px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; } .transition-form { margin-top: 12px; } label { display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: #56665e; } label.wide { grid-column: 1 / -1; } label :deep(.ant-select) { width: 100%; }
</style>
