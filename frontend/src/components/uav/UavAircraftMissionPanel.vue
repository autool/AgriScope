<script setup lang="ts">
import { message } from 'ant-design-vue'
import type { UploadProps } from 'ant-design-vue'
import { ref, shallowRef } from 'vue'

import type {
  AircraftUploadMetadata,
  MissionUploadMetadata,
  UavAircraft,
  UavMission,
  UavPolygon,
} from '@/types/uav'

defineProps<{
  aircraft: UavAircraft[]
  missions: UavMission[]
  selectedMissionCode: string | null
  canManageAircraft: boolean
  canManageMissions: boolean
  loading: boolean
}>()

const emit = defineEmits<{
  'select-mission': [missionCode: string]
  'register-aircraft': [file: File, metadata: AircraftUploadMetadata]
  'create-mission': [file: File, metadata: MissionUploadMetadata]
}>()

const aircraftModalOpenRef = ref<boolean>(false)
const missionModalOpenRef = ref<boolean>(false)
const certificateFileRef = shallowRef<File | null>(null)
const pilotLicenseFileRef = shallowRef<File | null>(null)
const aircraftCodeRef = ref<string>('')
const aircraftNameRef = ref<string>('')
const manufacturerRef = ref<string>('')
const modelNumberRef = ref<string>('')
const serialNumberRef = ref<string>('')
const registrationNumberRef = ref<string>('')
const sensorNameRef = ref<string>('')
const sensorModelRef = ref<string>('')
const sensorSerialRef = ref<string>('')
const ownerDepartmentRef = ref<string>('')

const missionCodeRef = ref<string>('')
const missionNameRef = ref<string>('')
const missionAircraftRef = ref<string>('')
const districtCodeRef = ref<string>('')
const boundaryJsonRef = ref<string>('')
const pilotNameRef = ref<string>('')
const pilotLicenseNumberRef = ref<string>('')
const plannedStartRef = ref<string>('')
const plannedEndRef = ref<string>('')
const altitudeRef = ref<number | null>(null)
const resolutionRef = ref<number | null>(null)
const forwardOverlapRef = ref<number | null>(null)
const sideOverlapRef = ref<number | null>(null)
const weatherNoteRef = ref<string>('')

const beforeCertificateUpload: UploadProps['beforeUpload'] = (file) => {
  certificateFileRef.value = file
  return false
}

const beforePilotLicenseUpload: UploadProps['beforeUpload'] = (file) => {
  pilotLicenseFileRef.value = file
  return false
}

const submitAircraft = (): void => {
  if (
    !certificateFileRef.value || !aircraftCodeRef.value || !aircraftNameRef.value
    || !manufacturerRef.value || !modelNumberRef.value || !serialNumberRef.value
    || !registrationNumberRef.value || !sensorNameRef.value || !sensorModelRef.value
    || !sensorSerialRef.value || !ownerDepartmentRef.value
  ) {
    message.warning('请完整填写航空器、传感器、权属信息并选择真实证书文件')
    return
  }
  emit('register-aircraft', certificateFileRef.value, {
    aircraftCode: aircraftCodeRef.value.trim(),
    aircraftName: aircraftNameRef.value.trim(),
    manufacturer: manufacturerRef.value.trim(),
    modelNumber: modelNumberRef.value.trim(),
    serialNumber: serialNumberRef.value.trim(),
    registrationNumber: registrationNumberRef.value.trim(),
    sensorName: sensorNameRef.value.trim(),
    sensorModel: sensorModelRef.value.trim(),
    sensorSerialNumber: sensorSerialRef.value.trim(),
    ownerDepartment: ownerDepartmentRef.value.trim(),
  })
  aircraftModalOpenRef.value = false
}

const submitMission = (): void => {
  if (
    !pilotLicenseFileRef.value || !missionCodeRef.value || !missionNameRef.value
    || !missionAircraftRef.value || !districtCodeRef.value || !boundaryJsonRef.value
    || !pilotNameRef.value || !pilotLicenseNumberRef.value || !plannedStartRef.value
    || !plannedEndRef.value || altitudeRef.value === null || resolutionRef.value === null
    || forwardOverlapRef.value === null || sideOverlapRef.value === null
    || !weatherNoteRef.value
  ) {
    message.warning('请完整填写任务范围、飞手资质、时间和航测参数')
    return
  }
  let boundary: UavPolygon
  try {
    boundary = JSON.parse(boundaryJsonRef.value) as UavPolygon
  } catch {
    message.warning('飞行范围必须是合法 GeoJSON Polygon')
    return
  }
  if (boundary.type !== 'Polygon') {
    message.warning('飞行范围必须是 GeoJSON Polygon')
    return
  }
  emit('create-mission', pilotLicenseFileRef.value, {
    missionCode: missionCodeRef.value.trim(),
    missionName: missionNameRef.value.trim(),
    aircraftCode: missionAircraftRef.value,
    districtCode: districtCodeRef.value.trim(),
    flightBoundary: boundary,
    pilotName: pilotNameRef.value.trim(),
    pilotLicenseNumber: pilotLicenseNumberRef.value.trim(),
    plannedStartAt: plannedStartRef.value.trim(),
    plannedEndAt: plannedEndRef.value.trim(),
    altitudeM: altitudeRef.value,
    expectedResolutionCm: resolutionRef.value,
    forwardOverlapPercent: forwardOverlapRef.value,
    sideOverlapPercent: sideOverlapRef.value,
    weatherNote: weatherNoteRef.value.trim(),
  })
  missionModalOpenRef.value = false
}
</script>

<template>
  <section class="resource-panel">
    <header>
      <div><small>AIRCRAFT & MISSIONS</small><h3>航空器与飞行任务</h3></div>
      <a-space>
        <a-button size="small" :disabled="!canManageAircraft" @click="aircraftModalOpenRef = true">登记航空器</a-button>
        <a-button
          size="small"
          type="primary"
          :disabled="!canManageMissions || !aircraft.some(item => item.status === 'active')"
          @click="missionModalOpenRef = true"
        >
          创建任务
        </a-button>
      </a-space>
    </header>
    <div class="aircraft-strip">
      <article v-for="item in aircraft" :key="item.aircraft_code">
        <span><strong>{{ item.aircraft_name }}</strong><em>{{ item.aircraft_code }} · {{ item.manufacturer }} {{ item.model_number }}</em></span>
        <a-tag :color="item.status === 'active' ? 'green' : 'default'">{{ item.status }}</a-tag>
        <p>{{ item.sensor_name }} / {{ item.sensor_model }} · 证书 {{ item.certificate_sha256.slice(0, 10) }}…</p>
      </article>
      <a-empty v-if="!aircraft.length" description="尚未上传航空器证书并登记真实航空器" />
    </div>
    <div class="mission-list">
      <button
        v-for="mission in missions"
        :key="mission.mission_code"
        type="button"
        :class="{ selected: selectedMissionCode === mission.mission_code }"
        @click="emit('select-mission', mission.mission_code)"
      >
        <span><strong>{{ mission.mission_name }}</strong><em>{{ mission.mission_code }} · {{ mission.district_name }}</em></span>
        <a-tag>{{ mission.status }}</a-tag>
        <p>{{ mission.planned_area_ha.toFixed(2) }} ha · {{ mission.altitude_m }} m · {{ mission.expected_resolution_cm }} cm</p>
      </button>
      <a-empty v-if="!missions.length" description="尚未创建真实无人机飞行任务" />
    </div>

    <a-modal
      v-model:open="aircraftModalOpenRef"
      title="上传证书并登记航空器"
      :confirm-loading="loading"
      width="760px"
      @ok="submitAircraft"
    >
      <div class="form-grid">
        <label><span>航空器编号</span><a-input v-model:value="aircraftCodeRef" /></label><label><span>航空器名称</span><a-input v-model:value="aircraftNameRef" /></label>
        <label><span>制造商</span><a-input v-model:value="manufacturerRef" /></label><label><span>型号</span><a-input v-model:value="modelNumberRef" /></label>
        <label><span>序列号</span><a-input v-model:value="serialNumberRef" /></label><label><span>登记编号</span><a-input v-model:value="registrationNumberRef" /></label>
        <label><span>传感器名称</span><a-input v-model:value="sensorNameRef" /></label><label><span>传感器型号</span><a-input v-model:value="sensorModelRef" /></label>
        <label><span>传感器序列号</span><a-input v-model:value="sensorSerialRef" /></label><label><span>权属单位</span><a-input v-model:value="ownerDepartmentRef" /></label>
        <label class="wide"><span>航空器登记/适航证书</span><a-upload :before-upload="beforeCertificateUpload" :max-count="1"><a-button>选择 PDF 或图片实体</a-button></a-upload></label>
      </div>
    </a-modal>

    <a-modal
      v-model:open="missionModalOpenRef"
      title="创建县界内无人机飞行任务"
      :confirm-loading="loading"
      width="780px"
      @ok="submitMission"
    >
      <div class="form-grid">
        <label><span>任务编号</span><a-input v-model:value="missionCodeRef" /></label><label><span>任务名称</span><a-input v-model:value="missionNameRef" /></label>
        <label><span>航空器</span><a-select v-model:value="missionAircraftRef" :options="aircraft.filter(item => item.status === 'active').map(item => ({ value: item.aircraft_code, label: `${item.aircraft_name} · ${item.aircraft_code}` }))" /></label><label><span>县区编码</span><a-input v-model:value="districtCodeRef" /></label>
        <label class="wide"><span>WGS84 飞行范围 GeoJSON Polygon</span><a-textarea v-model:value="boundaryJsonRef" :rows="4" placeholder="必须完整位于申报县区真实边界内" /></label>
        <label><span>飞手姓名</span><a-input v-model:value="pilotNameRef" /></label><label><span>飞手资质编号</span><a-input v-model:value="pilotLicenseNumberRef" /></label>
        <label class="wide"><span>飞手执照/资质实体</span><a-upload :before-upload="beforePilotLicenseUpload" :max-count="1"><a-button>选择 PDF 或图片实体</a-button></a-upload></label>
        <label><span>计划开始</span><a-input v-model:value="plannedStartRef" placeholder="ISO 8601，必须含时区" /></label><label><span>计划结束</span><a-input v-model:value="plannedEndRef" placeholder="ISO 8601，必须含时区" /></label>
        <label><span>航高（米）</span><a-input-number v-model:value="altitudeRef" :min="1" /></label><label><span>目标分辨率（厘米）</span><a-input-number v-model:value="resolutionRef" :min="0.1" /></label>
        <label><span>航向重叠度（%）</span><a-input-number v-model:value="forwardOverlapRef" :min="50" :max="100" /></label><label><span>旁向重叠度（%）</span><a-input-number v-model:value="sideOverlapRef" :min="30" :max="100" /></label>
        <label class="wide"><span>天气和作业条件</span><a-textarea v-model:value="weatherNoteRef" :rows="2" /></label>
      </div>
    </a-modal>
  </section>
</template>

<style scoped>
.resource-panel { display: flex; flex-direction: column; min-height: 0; padding: 12px; overflow: hidden; background: #fff; border: 1px solid #dfe5e2; border-radius: 8px; }
header { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 8px; } small { font-size: 8px; color: #718078; letter-spacing: 1px; } h3 { margin: 2px 0 0; font-size: 15px; color: #20352c; }
.aircraft-strip { display: grid; grid-template-columns: 1fr; gap: 5px; max-height: 175px; overflow: auto; }
.aircraft-strip article, .mission-list button { position: relative; padding: 8px; text-align: left; background: #f8faf9; border: 1px solid #e1e7e4; border-radius: 6px; }
.aircraft-strip span, .mission-list span { display: flex; flex-direction: column; padding-right: 60px; } strong { font-size: 11px; color: #294137; } em { overflow: hidden; font-size: 8px; font-style: normal; color: #7c8a83; text-overflow: ellipsis; white-space: nowrap; }
.aircraft-strip :deep(.ant-tag), .mission-list :deep(.ant-tag) { position: absolute; top: 7px; right: 5px; } p { margin: 5px 0 0; font-size: 8px; color: #87938d; }
.mission-list { display: flex; flex: 1; min-height: 0; flex-direction: column; gap: 5px; padding-top: 9px; overflow: auto; border-top: 1px solid #e7ece9; }
.mission-list button { width: 100%; cursor: pointer; } .mission-list button:hover, .mission-list button.selected { background: #eef8f2; border-color: #82bb9a; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; } label { display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: #56665e; } label.wide { grid-column: 1 / -1; } label :deep(.ant-input-number), label :deep(.ant-select) { width: 100%; }
</style>
