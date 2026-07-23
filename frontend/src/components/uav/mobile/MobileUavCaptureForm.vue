<script setup lang="ts">
import {
  AimOutlined,
  CameraOutlined,
  CheckCircleOutlined,
  EnvironmentOutlined,
  ReloadOutlined,
  RocketOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { useUavCaptureStore } from '@/store/uavCaptureStore'
import { useUserStore } from '@/store/userStore'
import type { UavMission } from '@/types/uav'

const captureStore = useUavCaptureStore()
const userStore = useUserStore()
const {
  canSubmitComputed,
  draftRef,
  errorMessageRef,
  loadingRef,
  missionsRef,
  onlineRef,
  photoFileRef,
  projectCodeRef,
  resultRef,
  secureContextRef,
  selectedMissionComputed,
  statusRef,
} = storeToRefs(captureStore)
const photoInputRef = ref<HTMLInputElement | null>(null)
const photoPreviewUrlRef = ref<string>('')

const findingTypeOptions = [
  '疑似病虫害',
  '作物倒伏',
  '洪涝积水',
  '旱情异常',
  '边界变化',
  '其他异常',
]
const severityOptions = [
  { value: 'minor', label: '一般', color: 'blue' },
  { value: 'major', label: '重要', color: 'orange' },
  { value: 'critical', label: '严重', color: 'red' },
] as const
const missionStatusLabels: Record<UavMission['status'], string> = {
  planned: '计划中',
  in_progress: '飞行采集中',
  captured: '已完成采集',
  processed: '已完成处理',
  reviewed: '已审核',
  cancelled: '已取消',
}
const operatorUsersComputed = computed(() => userStore.usersRef.filter(
  (user) => user.capabilities.includes('operate_uav_missions'),
))
const accuracyStateComputed = computed<'success' | 'warning' | 'error'>(() => {
  const accuracy = draftRef.value.location_accuracy_m
  if (accuracy === null) return 'error'
  if (accuracy <= 20) return 'success'
  if (accuracy <= 100) return 'warning'
  return 'error'
})
const statusLabelComputed = computed<string>(() => ({
  idle: '等待采集',
  locating: '正在定位',
  ready: '可以提交',
  submitting: '正在原子提交',
  completed: '采集已入库',
  error: '需要处理',
}[statusRef.value]))

watch(
  photoFileRef,
  (file) => {
    if (photoPreviewUrlRef.value) URL.revokeObjectURL(photoPreviewUrlRef.value)
    photoPreviewUrlRef.value = file ? URL.createObjectURL(file) : ''
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (photoPreviewUrlRef.value) URL.revokeObjectURL(photoPreviewUrlRef.value)
})

const selectPhoto = (event: Event): void => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] || null
  if (file && !['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
    message.warning('现场照片仅支持 JPEG、PNG 或 WebP')
    input.value = ''
    return
  }
  if (file && file.size > 20 * 1024 * 1024) {
    message.warning('移动采集照片不能超过 20 MB')
    input.value = ''
    return
  }
  captureStore.setPhoto(file)
}

const changeOperator = async (userCode: string): Promise<void> => {
  userStore.setCurrentUser(userCode)
  try {
    await captureStore.load()
  } catch {
    message.warning(errorMessageRef.value || '无法加载可采集任务')
  }
}

const captureLocation = async (): Promise<void> => {
  try {
    await captureStore.captureLocation()
    message.success('GPS 坐标、终端精度和采集时间已记录')
  } catch {
    message.warning(errorMessageRef.value || '无法获取 GPS 位置')
  }
}

const submit = async (): Promise<void> => {
  try {
    const result = await captureStore.submit()
    message.success(
      result.idempotent_replay
        ? '相同移动采集已安全重放，没有生成重复证据'
        : '照片实体与空间疑点已原子入库',
    )
  } catch {
    message.warning(errorMessageRef.value || '移动采集提交失败，可使用原编号重试')
  }
}
</script>

<template>
  <main class="capture-card">
    <header class="capture-heading">
      <span class="heading-icon"><RocketOutlined /></span>
      <span>
        <small>AGRISCOPE UAV FIELD</small>
        <strong>无人机移动疑点采集</strong>
        <em>{{ projectCodeRef }} · GPS、照片实体与空间疑点原子提交</em>
      </span>
      <a-tag :color="onlineRef ? 'green' : 'red'">
        {{ onlineRef ? '网络在线' : '当前离线' }}
      </a-tag>
    </header>

    <a-alert
      v-if="!onlineRef"
      type="warning"
      show-icon
      message="当前处于离线状态"
      description="业务草稿会保存在本机，但照片不会被宣称为已离线入库；恢复网络并重新确认照片后再提交。"
    />
    <a-alert
      v-else-if="!secureContextRef"
      type="error"
      show-icon
      message="当前页面不是 HTTPS 安全连接"
      description="浏览器会阻止现场 GPS；请通过 HTTPS 网关打开无人机移动采集页面。"
    />

    <section class="capture-section identity-section">
      <div class="section-title">
        <span><strong>采集身份</strong><small>稳定用户能力由服务端项目成员目录决定</small></span>
        <a-tag>{{ statusLabelComputed }}</a-tag>
      </div>
      <a-select
        :value="userStore.currentUserComputed?.user_code"
        :loading="userStore.loadingRef"
        placeholder="选择无人机采集人员"
        @change="changeOperator"
      >
        <a-select-option
          v-for="user in operatorUsersComputed"
          :key="user.user_code"
          :value="user.user_code"
        >
          {{ user.display_name }} · {{ user.role_name }}
        </a-select-option>
      </a-select>
      <small class="audit-hint">
        稳定用户编码：{{ userStore.currentUserComputed?.user_code || '--' }}
      </small>
    </section>

    <section class="capture-section mission-section">
      <div class="section-title">
        <span><strong>飞行任务</strong><small>只列出已启动、已采集或已处理任务</small></span>
        <EnvironmentOutlined />
      </div>
      <a-select
        :value="draftRef.mission_code"
        :loading="loadingRef"
        :disabled="!missionsRef.length"
        placeholder="选择当前飞行任务"
        @change="captureStore.selectMission"
      >
        <a-select-option
          v-for="mission in missionsRef"
          :key="mission.mission_code"
          :value="mission.mission_code"
        >
          {{ mission.mission_name }} · {{ mission.district_name }}
        </a-select-option>
      </a-select>
      <div v-if="selectedMissionComputed" class="mission-summary">
        <span><small>任务编号</small><strong>{{ selectedMissionComputed.mission_code }}</strong></span>
        <span><small>当前状态</small><strong>{{ missionStatusLabels[selectedMissionComputed.status] }}</strong></span>
        <span><small>航空器</small><strong>{{ selectedMissionComputed.aircraft_name }}</strong></span>
        <span><small>计划范围</small><strong>{{ selectedMissionComputed.planned_area_ha.toFixed(2) }} ha</strong></span>
      </div>
      <a-empty
        v-else
        :image="false"
        description="没有可执行移动采集的任务；请先在桌面端创建并启动飞行任务"
      />
    </section>

    <section class="capture-section location-section">
      <div class="section-title">
        <span><strong>现场 GPS</strong><small>服务端再次校验坐标位于所选任务 Polygon 内</small></span>
        <AimOutlined />
      </div>
      <div v-if="draftRef.longitude !== null" class="location-grid">
        <div><small>经度</small><strong>{{ draftRef.longitude.toFixed(6) }}</strong></div>
        <div><small>纬度</small><strong>{{ draftRef.latitude?.toFixed(6) }}</strong></div>
        <div :class="['accuracy', accuracyStateComputed]"><small>定位精度</small><strong>± {{ draftRef.location_accuracy_m }} m</strong></div>
        <div><small>采集时间</small><strong>{{ draftRef.captured_at?.slice(0, 19).replace('T', ' ') }}</strong></div>
      </div>
      <a-button
        block
        type="primary"
        ghost
        :disabled="!selectedMissionComputed"
        :loading="statusRef === 'locating'"
        @click="captureLocation"
      >
        <template #icon><AimOutlined /></template>
        {{ draftRef.longitude === null ? '获取当前 GPS 位置' : '重新定位' }}
      </a-button>
      <p v-if="draftRef.location_accuracy_m && draftRef.location_accuracy_m > 100" class="accuracy-warning">
        当前定位误差超过 100 米，建议移动到开阔区域后重试；平台保存真实精度，不会伪造高精度定位。
      </p>
    </section>

    <section class="capture-section">
      <div class="section-title">
        <span><strong>疑点判读</strong><small>分类是现场记录，最终结论仍需审核人员复核</small></span>
      </div>
      <div class="field-grid">
        <label>
          <span>疑点类型</span>
          <a-select v-model:value="draftRef.finding_type" placeholder="请选择">
            <a-select-option v-for="item in findingTypeOptions" :key="item" :value="item">
              {{ item }}
            </a-select-option>
          </a-select>
        </label>
        <label>
          <span>严重程度</span>
          <a-select v-model:value="draftRef.severity" placeholder="请选择">
            <a-select-option v-for="item in severityOptions" :key="item.value" :value="item.value">
              {{ item.label }}
            </a-select-option>
          </a-select>
        </label>
      </div>
      <label class="wide-field">
        <span>关联图斑编号（可选）</span>
        <a-input
          v-model:value="draftRef.plot_code"
          :maxlength="50"
          placeholder="填写后由服务端校验属于当前作业任务"
        />
      </label>
      <label class="wide-field">
        <span>现场说明</span>
        <a-textarea
          v-model:value="draftRef.description"
          :maxlength="3000"
          :auto-size="{ minRows: 3, maxRows: 7 }"
          placeholder="记录异常形态、范围、作物表现和需要复核的原因"
        />
      </label>
    </section>

    <section class="capture-section photo-section">
      <div class="section-title">
        <span><strong>现场照片实体</strong><small>服务端校验图像签名、20 MB 上限、大小和 SHA-256</small></span>
        <CameraOutlined />
      </div>
      <button class="photo-picker" type="button" @click="photoInputRef?.click()">
        <img v-if="photoPreviewUrlRef" :src="photoPreviewUrlRef" alt="待上传无人机现场照片预览">
        <span v-else><CameraOutlined /><strong>拍照或选择照片</strong><small>JPEG / PNG / WebP</small></span>
      </button>
      <input
        ref="photoInputRef"
        class="hidden-file"
        type="file"
        accept="image/jpeg,image/png,image/webp"
        capture="environment"
        @change="selectPhoto"
      >
      <p v-if="photoFileRef" class="photo-meta">
        {{ photoFileRef.name }} · {{ (photoFileRef.size / 1024 / 1024).toFixed(2) }} MB
      </p>
    </section>

    <a-alert
      v-if="errorMessageRef"
      type="error"
      show-icon
      :message="errorMessageRef"
      :description="`采集编号 ${draftRef.capture_code} 已保留；修正问题后使用同一编号重试，服务端会执行幂等校验。`"
    />
    <a-alert
      v-if="resultRef"
      type="success"
      show-icon
      :message="resultRef.idempotent_replay ? '相同采集已安全重放' : '移动采集已原子入库'"
      :description="`疑点 ${resultRef.finding.finding_code} · 状态 ${resultRef.finding.status} · 照片 SHA-256 ${resultRef.artifact.checksum_sha256}`"
    />

    <div class="submit-bar">
      <a-button
        type="primary"
        size="large"
        block
        :disabled="!canSubmitComputed"
        :loading="statusRef === 'submitting'"
        @click="submit"
      >
        <template #icon><CheckCircleOutlined /></template>
        原子提交照片与空间疑点
      </a-button>
      <a-button
        v-if="resultRef"
        block
        @click="captureStore.resetDraft()"
      >
        <template #icon><ReloadOutlined /></template>
        继续采集下一处疑点
      </a-button>
    </div>
  </main>
</template>

<style scoped lang="less">
.capture-card { width: min(100%, 640px); padding: 16px; margin: 0 auto; }
.capture-heading { display: grid; grid-template-columns: 42px minmax(0, 1fr) auto; gap: 10px; align-items: center; padding: 16px; color: #fff; background: #17342b; border-radius: 16px; }
.capture-heading > span:not(.heading-icon) { display: flex; flex-direction: column; min-width: 0; }
.capture-heading small { font-size: 9px; letter-spacing: .12em; color: #92cbb0; }
.capture-heading strong { margin-top: 2px; font-size: 18px; }
.capture-heading em { overflow: hidden; margin-top: 2px; font-size: 10px; font-style: normal; color: rgb(255 255 255 / 58%); text-overflow: ellipsis; white-space: nowrap; }
.heading-icon { display: grid; place-items: center; width: 42px; height: 42px; font-size: 20px; color: #e0be58; background: rgb(255 255 255 / 8%); border: 1px solid rgb(255 255 255 / 12%); border-radius: 12px; }
.capture-card > .ant-alert { margin-top: 12px; }
.capture-section { padding: 14px; margin-top: 12px; background: #fff; border: 1px solid #dce5e1; border-radius: 14px; }
.section-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; color: #315a49; }
.section-title > span { display: flex; flex-direction: column; }
.section-title strong { font-size: 13px; color: #20382e; }
.section-title small, .audit-hint { font-size: 9px; color: #82918a; }
.identity-section .ant-select, .mission-section > .ant-select { width: 100%; }
.audit-hint { display: block; margin-top: 6px; }
.mission-summary, .location-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px; }
.mission-summary > span, .location-grid > div { display: flex; min-width: 0; flex-direction: column; padding: 9px; background: #f4f7f5; border-radius: 9px; }
.mission-summary small, .location-grid small { font-size: 9px; color: #839089; }
.mission-summary strong, .location-grid strong { overflow: hidden; margin-top: 3px; font-size: 11px; color: #30463b; text-overflow: ellipsis; white-space: nowrap; }
.location-grid { margin-top: 0; margin-bottom: 10px; }
.location-grid .accuracy.success strong { color: #31885e; }
.location-grid .accuracy.warning strong { color: #b16c1f; }
.location-grid .accuracy.error strong { color: #bf4545; }
.accuracy-warning { margin: 8px 0 0; font-size: 10px; line-height: 1.5; color: #a35f1b; }
.field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.field-grid label, .wide-field { display: flex; flex-direction: column; gap: 5px; font-size: 10px; color: #65736c; }
.wide-field { margin-top: 10px; }
.photo-picker { display: grid; place-items: center; width: 100%; min-height: 190px; padding: 0; overflow: hidden; color: #476758; cursor: pointer; background: #f1f6f3; border: 1px dashed #a8bdb2; border-radius: 12px; }
.photo-picker img { width: 100%; max-height: 340px; object-fit: cover; }
.photo-picker span { display: flex; flex-direction: column; align-items: center; gap: 5px; }
.photo-picker span > :first-child { font-size: 26px; }
.photo-picker small { font-size: 9px; color: #91a098; }
.hidden-file { display: none; }
.photo-meta { margin: 8px 0 0; font-size: 10px; color: #708078; }
.submit-bar { position: sticky; bottom: 0; display: grid; gap: 8px; padding: 12px 0 4px; background: linear-gradient(to bottom, transparent, #edf2f0 18%); }
@media (max-width: 520px) {
  .capture-card { padding: 10px; }
  .capture-heading { grid-template-columns: 38px minmax(0, 1fr); border-radius: 12px; }
  .capture-heading > .ant-tag { grid-column: 1 / -1; justify-self: start; }
  .field-grid { grid-template-columns: 1fr; }
}
</style>
