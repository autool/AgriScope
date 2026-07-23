<script setup lang="ts">
import { MobileOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, ref, watch } from 'vue'

import UavAircraftMissionPanel from '@/components/uav/UavAircraftMissionPanel.vue'
import UavArtifactPanel from '@/components/uav/UavArtifactPanel.vue'
import UavAuditPanel from '@/components/uav/UavAuditPanel.vue'
import UavFindingPanel from '@/components/uav/UavFindingPanel.vue'
import UavMissionMap from '@/components/uav/UavMissionMap.vue'
import { useUavStore } from '@/store/uavStore'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  AircraftUploadMetadata,
  ArtifactUploadMetadata,
  MissionUploadMetadata,
  UavFindingCreatePayload,
  UavMissionAction,
  UavPolygon,
} from '@/types/uav'

const uavStore = useUavStore()
const userStore = useUserStore()
const workbenchStore = useWorkbenchStore()
const {
  canDownloadComputed,
  canManageAircraftComputed,
  canManageMissionsComputed,
  canOperateComputed,
  canReviewComputed,
  loadingRef,
  mutatingRef,
  overviewRef,
} = storeToRefs(uavStore)
const selectedMissionCodeRef = ref<string | null>(null)
const draftBoundaryRef = ref<UavPolygon | null>(null)
const pickedCoordinateRef = ref<{ lon: number; lat: number } | null>(null)
const selectedMissionComputed = computed(() => (
  overviewRef.value?.missions.find(
    (item) => item.mission_code === selectedMissionCodeRef.value,
  ) || overviewRef.value?.missions[0] || null
))
const mobileCaptureUrlComputed = computed(() => (
  `/uav-capture?project_code=${encodeURIComponent(workbenchStore.projectCodeComputed)}`
))

const loadOverview = async (): Promise<void> => {
  try {
    await uavStore.load()
  } catch {
    // 请求层已展示安全错误，页面保留数据库真实空态。
  }
}

watch(
  () => userStore.currentUserComputed?.user_code,
  (userCode) => {
    if (userCode) void loadOverview()
  },
  { immediate: true },
)

watch(() => overviewRef.value?.missions, (missions) => {
  if (!missions?.length) {
    selectedMissionCodeRef.value = null
    return
  }
  if (!missions.some((item) => item.mission_code === selectedMissionCodeRef.value)) {
    selectedMissionCodeRef.value = missions[0].mission_code
  }
}, { deep: true })

const runAction = async (
  action: () => Promise<void>,
  successMessage: string,
  afterSuccess?: () => void,
): Promise<void> => {
  try {
    await action()
    afterSuccess?.()
    message.success(successMessage)
  } catch {
    // 请求层已统一展示后端安全错误信息，避免未处理 Promise。
  }
}

const handleRegisterAircraft = (
  file: File,
  metadata: AircraftUploadMetadata,
): void => {
  void runAction(
    () => uavStore.registerAircraft(file, metadata),
    '航空器、传感器身份及证书实体已登记',
  )
}

const handleCreateMission = (
  file: File,
  metadata: MissionUploadMetadata,
): void => {
  void runAction(
    () => uavStore.createMission(file, metadata),
    '飞行任务已通过真实县界校验并创建',
    () => { draftBoundaryRef.value = null },
  )
}

const handleUploadArtifact = (
  missionCode: string,
  file: File,
  metadata: ArtifactUploadMetadata,
): void => {
  void runAction(
    () => uavStore.uploadArtifact(missionCode, file, metadata),
    '无人机实体成果已完成大小与 SHA-256 校验',
  )
}

const handleTransition = (
  missionCode: string,
  action: UavMissionAction,
  comment: string,
  actualTime: string | null,
): void => {
  void runAction(
    () => uavStore.transition(missionCode, action, comment, actualTime),
    '任务状态已按成果与疑点门禁更新',
  )
}

const handleCreateFinding = (
  missionCode: string,
  payload: Omit<UavFindingCreatePayload, 'operator_code'>,
): void => {
  void runAction(
    () => uavStore.createFinding(missionCode, payload),
    '空间疑点已绑定任务实体成果并进入复核队列',
    () => { pickedCoordinateRef.value = null },
  )
}

const handleReviewFinding = (
  missionCode: string,
  findingCode: string,
  decision: 'confirm' | 'dismiss',
  comment: string,
): void => {
  void runAction(
    () => uavStore.reviewFinding(missionCode, findingCode, decision, comment),
    decision === 'confirm' ? '无人机疑点已人工确认' : '无人机疑点已依据证据排除',
  )
}

const handleDownload = (artifactCode: string, filename: string): void => {
  void runAction(
    () => uavStore.downloadArtifact(artifactCode, filename),
    '成果校验通过，已开始下载',
  )
}
</script>

<template>
  <div class="uav-view">
    <section class="mobile-entry">
      <span>
        <small>MOBILE FIELD CAPTURE</small>
        <strong>无人机现场疑点移动采集</strong>
        <em>任务启动后，通过手机 GPS 将现场照片实体与空间疑点一次提交</em>
      </span>
      <a-button type="primary" :href="mobileCaptureUrlComputed" target="_blank">
        <MobileOutlined /> 打开移动采集端
      </a-button>
    </section>
    <section class="summary-strip">
      <span><small>AIRCRAFT</small><strong>{{ overviewRef?.aircraft_count || 0 }}</strong><em>真实航空器</em></span>
      <span><small>MISSIONS</small><strong>{{ overviewRef?.mission_count || 0 }}</strong><em>{{ overviewRef?.active_mission_count || 0 }} 个执行中</em></span>
      <span><small>PROCESSING</small><strong>{{ overviewRef?.pending_processing_count || 0 }}</strong><em>待处理任务</em></span>
      <span><small>ARTIFACTS</small><strong>{{ overviewRef?.verified_artifact_count || 0 }}</strong><em>校验通过实体</em></span>
      <span><small>FINDINGS</small><strong>{{ overviewRef?.pending_finding_count || 0 }}</strong><em>待人工复核</em></span>
      <span><small>AUDIT</small><strong>{{ overviewRef?.events.length || 0 }}</strong><em>不可变事件</em></span>
    </section>
    <a-spin :spinning="loadingRef" class="workspace-spin">
      <section class="workspace-grid">
        <UavMissionMap
          class="map-slot"
          :missions="overviewRef?.missions || []"
          :findings="overviewRef?.findings || []"
          :selected-mission-code="selectedMissionComputed?.mission_code || null"
          :draft-boundary="draftBoundaryRef"
          :picked-coordinate="pickedCoordinateRef"
          :can-plan="canManageMissionsComputed"
          :can-register-finding="canOperateComputed"
          @select-mission="selectedMissionCodeRef = $event"
          @boundary-drawn="draftBoundaryRef = $event"
          @boundary-cleared="draftBoundaryRef = null"
          @finding-coordinate-picked="pickedCoordinateRef = $event"
          @finding-coordinate-cleared="pickedCoordinateRef = null"
        />
        <UavAircraftMissionPanel
          class="aircraft-slot"
          :aircraft="overviewRef?.aircraft || []"
          :missions="overviewRef?.missions || []"
          :selected-mission-code="selectedMissionComputed?.mission_code || null"
          :draft-boundary="draftBoundaryRef"
          :can-manage-aircraft="canManageAircraftComputed"
          :can-manage-missions="canManageMissionsComputed"
          :loading="mutatingRef"
          @select-mission="selectedMissionCodeRef = $event"
          @register-aircraft="handleRegisterAircraft"
          @create-mission="handleCreateMission"
        />
        <UavArtifactPanel
          class="artifact-slot"
          :mission="selectedMissionComputed"
          :artifacts="overviewRef?.artifacts || []"
          :can-operate="canOperateComputed"
          :can-review="canReviewComputed"
          :can-download="canDownloadComputed"
          :loading="mutatingRef"
          @upload-artifact="handleUploadArtifact"
          @transition="handleTransition"
          @download="handleDownload"
        />
        <UavFindingPanel
          class="finding-slot"
          :mission="selectedMissionComputed"
          :artifacts="overviewRef?.artifacts || []"
          :findings="overviewRef?.findings || []"
          :picked-coordinate="pickedCoordinateRef"
          :can-operate="canOperateComputed"
          :can-review="canReviewComputed"
          :loading="mutatingRef"
          @create-finding="handleCreateFinding"
          @review-finding="handleReviewFinding"
        />
        <UavAuditPanel class="audit-slot" :events="overviewRef?.events || []" />
      </section>
    </a-spin>
  </div>
</template>

<style scoped>
.uav-view { display: grid; grid-template-rows: auto auto minmax(0, 1fr); gap: 10px; height: 100%; padding: 10px; background: #eef2f0; }
.mobile-entry { display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; background: #eef7f2; border: 1px solid #cfe2d7; border-radius: 8px; }
.mobile-entry span { display: flex; min-width: 0; flex-direction: column; }
.mobile-entry small { font-size: 7px; color: #6f8e7e; letter-spacing: .8px; }
.mobile-entry strong { font-size: 12px; color: #2f5a44; }
.mobile-entry em { overflow: hidden; font-size: 9px; font-style: normal; color: #708078; text-overflow: ellipsis; white-space: nowrap; }
.summary-strip { display: grid; grid-template-columns: repeat(6, minmax(110px, 1fr)); gap: 7px; }
.summary-strip span { display: flex; flex-direction: column; padding: 9px 11px; background: #fff; border: 1px solid #dfe5e2; border-radius: 7px; }
.summary-strip small { font-size: 7px; color: #8b9791; letter-spacing: .8px; }
.summary-strip strong { font-size: 19px; color: #347958; }
.summary-strip em { font-size: 8px; font-style: normal; color: #77867e; }
.workspace-spin { min-height: 0; }
.workspace-spin :deep(.ant-spin-container) { height: 100%; min-height: 0; }
.workspace-grid { display: grid; grid-template-rows: minmax(0, 1fr) minmax(220px, .72fr); grid-template-columns: minmax(430px, 1.15fr) minmax(330px, .9fr) minmax(360px, 1fr); gap: 9px; height: 100%; min-height: 0; }
.map-slot { grid-row: 1 / 3; grid-column: 1; }
.aircraft-slot { grid-row: 1; grid-column: 2; }
.artifact-slot { grid-row: 1; grid-column: 3; }
.finding-slot { grid-row: 2; grid-column: 2; }
.audit-slot { grid-row: 2; grid-column: 3; }
@media (max-width: 1320px) { .workspace-grid { grid-template-rows: 520px 620px 430px; grid-template-columns: 1fr 1fr; min-height: 1570px; overflow: auto; } .map-slot { grid-row: 1; grid-column: 1 / -1; } .aircraft-slot { grid-row: 2; grid-column: 1; } .artifact-slot { grid-row: 2; grid-column: 2; } .finding-slot { grid-row: 3; grid-column: 1; } .audit-slot { grid-row: 3; grid-column: 2; } }
</style>
