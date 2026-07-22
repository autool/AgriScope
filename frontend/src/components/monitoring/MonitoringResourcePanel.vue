<script setup lang="ts">
import { message } from 'ant-design-vue'
import { computed, ref } from 'vue'

import type {
  DeviceCreatePayload,
  DeviceType,
  MonitoringDevice,
  MonitoringStation,
  StationCreatePayload,
  StationType,
} from '@/types/monitoringNetwork'

const props = defineProps<{
  stations: MonitoringStation[]
  devices: MonitoringDevice[]
  selectedDeviceCode: string | null
  canManage: boolean
  loading: boolean
}>()

const emit = defineEmits<{
  'select-device': [deviceCode: string]
  'register-station': [payload: Omit<StationCreatePayload, 'operator_code'>]
  'register-device': [stationCode: string, payload: Omit<DeviceCreatePayload, 'operator_code'>]
}>()

const stationModalOpenRef = ref<boolean>(false)
const deviceModalOpenRef = ref<boolean>(false)
const stationCodeRef = ref<string>('')
const stationNameRef = ref<string>('')
const districtCodeRef = ref<string>('')
const longitudeRef = ref<number | null>(null)
const latitudeRef = ref<number | null>(null)
const stationTypeRef = ref<StationType>('comprehensive')
const ownerDepartmentRef = ref<string>('')
const sourceNameRef = ref<string>('')
const sourceUriRef = ref<string>('')
const sourceVersionRef = ref<string>('')
const stationEvidenceUriRef = ref<string>('')
const stationEvidenceSizeRef = ref<number | null>(null)
const stationEvidenceShaRef = ref<string>('')

const deviceStationCodeRef = ref<string>('')
const deviceCodeRef = ref<string>('')
const deviceNameRef = ref<string>('')
const deviceTypeRef = ref<DeviceType>('weather_sensor')
const vendorRef = ref<string>('')
const modelNumberRef = ref<string>('')
const serialNumberRef = ref<string>('')
const deviceOwnerRef = ref<string>('')
const installedAtRef = ref<string>('')
const photoUriRef = ref<string>('')
const photoSizeRef = ref<number | null>(null)
const photoShaRef = ref<string>('')

const deviceGroupsComputed = computed(() => props.stations.map((station) => ({
  station,
  devices: props.devices.filter((item) => item.station_code === station.station_code),
})))

const submitStation = (): void => {
  if (
    !stationCodeRef.value || !stationNameRef.value || !districtCodeRef.value
    || longitudeRef.value === null || latitudeRef.value === null
    || !ownerDepartmentRef.value || !sourceNameRef.value || !sourceUriRef.value
    || !sourceVersionRef.value || !stationEvidenceUriRef.value
    || !stationEvidenceSizeRef.value || stationEvidenceShaRef.value.length !== 64
  ) {
    message.warning('请完整填写站点坐标、来源和实体证据，SHA-256 必须为 64 位')
    return
  }
  emit('register-station', {
    station_code: stationCodeRef.value.trim(),
    station_name: stationNameRef.value.trim(),
    district_code: districtCodeRef.value.trim(),
    longitude: longitudeRef.value,
    latitude: latitudeRef.value,
    station_type: stationTypeRef.value,
    owner_department: ownerDepartmentRef.value.trim(),
    source_name: sourceNameRef.value.trim(),
    source_uri: sourceUriRef.value.trim(),
    source_version: sourceVersionRef.value.trim(),
    evidence_uri: stationEvidenceUriRef.value.trim(),
    evidence_size_bytes: stationEvidenceSizeRef.value,
    evidence_sha256: stationEvidenceShaRef.value.trim(),
    status: 'active',
  })
  stationModalOpenRef.value = false
}

const submitDevice = (): void => {
  if (
    !deviceStationCodeRef.value || !deviceCodeRef.value || !deviceNameRef.value
    || !vendorRef.value || !modelNumberRef.value || !serialNumberRef.value
    || !deviceOwnerRef.value || !installedAtRef.value || !photoUriRef.value
    || !photoSizeRef.value || photoShaRef.value.length !== 64
  ) {
    message.warning('请完整填写设备身份、带时区安装时间和照片实体证据')
    return
  }
  emit('register-device', deviceStationCodeRef.value, {
    device_code: deviceCodeRef.value.trim(),
    device_name: deviceNameRef.value.trim(),
    device_type: deviceTypeRef.value,
    vendor: vendorRef.value.trim(),
    model_number: modelNumberRef.value.trim(),
    serial_number: serialNumberRef.value.trim(),
    owner_department: deviceOwnerRef.value.trim(),
    installed_at: installedAtRef.value.trim(),
    photo_uri: photoUriRef.value.trim(),
    photo_size_bytes: photoSizeRef.value,
    photo_sha256: photoShaRef.value.trim(),
    status: 'offline',
  })
  deviceModalOpenRef.value = false
}
</script>

<template>
  <section class="resource-panel">
    <header>
      <div><small>FIELD NETWORK</small><h3>站点与设备资源树</h3></div>
      <a-space>
        <a-button size="small" :disabled="!canManage" @click="stationModalOpenRef = true">登记站点</a-button>
        <a-button
          size="small"
          type="primary"
          :disabled="!canManage || !stations.length"
          @click="deviceModalOpenRef = true"
        >
          登记设备
        </a-button>
      </a-space>
    </header>
    <a-alert
      v-if="!canManage"
      type="info"
      show-icon
      message="当前身份可查看真实监测资源，只有项目负责人可登记站点和设备。"
    />
    <div v-if="deviceGroupsComputed.length" class="resource-tree">
      <article v-for="group in deviceGroupsComputed" :key="group.station.station_code">
        <div class="station-row">
          <span><strong>{{ group.station.station_name }}</strong><em>{{ group.station.station_code }}</em></span>
          <a-tag>{{ group.station.district_name }}</a-tag>
        </div>
        <p>{{ group.station.longitude.toFixed(6) }}, {{ group.station.latitude.toFixed(6) }} · {{ group.station.source_name }} / {{ group.station.source_version }}</p>
        <button
          v-for="device in group.devices"
          :key="device.device_code"
          type="button"
          class="device-row"
          :class="{ selected: selectedDeviceCode === device.device_code }"
          @click="emit('select-device', device.device_code)"
        >
          <span><strong>{{ device.device_name }}</strong><em>{{ device.device_code }} · {{ device.device_type }}</em></span>
          <a-badge :status="device.status === 'online' ? 'success' : device.status === 'abnormal' ? 'error' : 'default'" :text="device.status" />
        </button>
        <a-empty v-if="!group.devices.length" :image="null" description="该站点尚未登记设备" />
      </article>
    </div>
    <a-empty v-else description="尚未登记真实监测站；平台不会预置虚构站点或设备" />

    <a-modal
      v-model:open="stationModalOpenRef"
      title="登记真实田间监测站"
      :confirm-loading="loading"
      width="760px"
      @ok="submitStation"
    >
      <div class="form-grid">
        <label><span>站点编号</span><a-input v-model:value="stationCodeRef" /></label>
        <label><span>站点名称</span><a-input v-model:value="stationNameRef" /></label>
        <label><span>县区编码</span><a-input v-model:value="districtCodeRef" placeholder="必须与坐标命中的真实县界一致" /></label>
        <label><span>站点类型</span><a-select
          v-model:value="stationTypeRef"
          :options="[
            { value: 'weather', label: '气象' }, { value: 'soil', label: '土壤' }, { value: 'crop', label: '作物' }, { value: 'pest', label: '病虫害' }, { value: 'comprehensive', label: '综合' },
          ]"
        /></label>
        <label><span>WGS84 经度</span><a-input-number v-model:value="longitudeRef" :precision="7" /></label>
        <label><span>WGS84 纬度</span><a-input-number v-model:value="latitudeRef" :precision="7" /></label>
        <label class="wide"><span>权属单位</span><a-input v-model:value="ownerDepartmentRef" /></label>
        <label><span>来源名称</span><a-input v-model:value="sourceNameRef" /></label>
        <label><span>来源版本</span><a-input v-model:value="sourceVersionRef" /></label>
        <label class="wide"><span>来源地址</span><a-input v-model:value="sourceUriRef" /></label>
        <label class="wide"><span>站点照片/验收证据 URI</span><a-input v-model:value="stationEvidenceUriRef" /></label>
        <label><span>证据大小（字节）</span><a-input-number v-model:value="stationEvidenceSizeRef" :min="1" /></label>
        <label><span>证据 SHA-256</span><a-input v-model:value="stationEvidenceShaRef" :maxlength="64" /></label>
      </div>
    </a-modal>

    <a-modal
      v-model:open="deviceModalOpenRef"
      title="登记真实监测设备"
      :confirm-loading="loading"
      width="760px"
      @ok="submitDevice"
    >
      <div class="form-grid">
        <label><span>所属站点</span><a-select v-model:value="deviceStationCodeRef" :options="stations.map(item => ({ value: item.station_code, label: `${item.station_name} · ${item.station_code}` }))" /></label>
        <label><span>设备类型</span><a-select
          v-model:value="deviceTypeRef"
          :options="[
            { value: 'weather_sensor', label: '气象传感器' }, { value: 'soil_sensor', label: '土壤传感器' }, { value: 'camera', label: '监控相机' }, { value: 'insect_trap', label: '虫情测报灯' }, { value: 'spore_trap', label: '孢子捕捉仪' }, { value: 'gateway', label: '物联网网关' }, { value: 'other', label: '其他' },
          ]"
        /></label>
        <label><span>设备编号</span><a-input v-model:value="deviceCodeRef" /></label>
        <label><span>设备名称</span><a-input v-model:value="deviceNameRef" /></label>
        <label><span>厂商</span><a-input v-model:value="vendorRef" /></label>
        <label><span>型号</span><a-input v-model:value="modelNumberRef" /></label>
        <label><span>序列号</span><a-input v-model:value="serialNumberRef" /></label>
        <label><span>安装时间</span><a-input v-model:value="installedAtRef" placeholder="ISO 8601，必须包含时区" /></label>
        <label class="wide"><span>权属单位</span><a-input v-model:value="deviceOwnerRef" /></label>
        <label class="wide"><span>设备照片 URI</span><a-input v-model:value="photoUriRef" /></label>
        <label><span>照片大小（字节）</span><a-input-number v-model:value="photoSizeRef" :min="1" /></label>
        <label><span>照片 SHA-256</span><a-input v-model:value="photoShaRef" :maxlength="64" /></label>
      </div>
    </a-modal>
  </section>
</template>

<style scoped>
.resource-panel { display: flex; flex-direction: column; min-height: 0; padding: 12px; overflow: hidden; background: #fff; border: 1px solid #dfe5e2; border-radius: 8px; }
header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
small { font-size: 8px; color: #718078; letter-spacing: 1px; }
h3 { margin: 2px 0 0; font-size: 15px; color: #20352c; }
.resource-tree { display: flex; flex: 1; flex-direction: column; gap: 9px; padding-top: 10px; overflow: auto; }
article { padding: 9px; border: 1px solid #e1e7e4; border-radius: 7px; }
.station-row, .device-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.station-row span, .device-row span { display: flex; min-width: 0; flex-direction: column; text-align: left; }
strong { font-size: 12px; color: #294137; }
em { overflow: hidden; font-size: 9px; font-style: normal; color: #7c8a83; text-overflow: ellipsis; white-space: nowrap; }
p { margin: 5px 0 7px; font-size: 9px; color: #87938d; }
.device-row { width: 100%; padding: 7px 8px; margin-top: 4px; cursor: pointer; background: #f8faf9; border: 1px solid transparent; border-radius: 6px; }
.device-row:hover, .device-row.selected { background: #eef8f2; border-color: #8fc6a7; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
label { display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: #56665e; }
label.wide { grid-column: 1 / -1; }
label :deep(.ant-input-number), label :deep(.ant-select) { width: 100%; }
</style>
