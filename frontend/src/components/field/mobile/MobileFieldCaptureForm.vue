<script setup lang="ts">
import {
  AimOutlined,
  CameraOutlined,
  CheckCircleOutlined,
  CloudSyncOutlined,
  EnvironmentOutlined,
  ReloadOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { useFieldCaptureStore } from '@/store/fieldCaptureStore'
import { useUserStore } from '@/store/userStore'

const captureStore = useFieldCaptureStore()
const userStore = useUserStore()
const {
  canSubmitComputed,
  draftRef,
  errorMessageRef,
  onlineRef,
  pendingUploadRef,
  photoFileRef,
  resultRef,
  secureContextRef,
  statusRef,
  taskCodeRef,
} = storeToRefs(captureStore)
const photoInputRef = ref<HTMLInputElement | null>(null)
const photoPreviewUrlRef = ref<string>('')

const landClassOptions = ['耕地', '园地', '林地', '草地', '水域', '建设用地']
const cropTypeOptions = ['水稻', '玉米', '小麦', '大豆', '马铃薯', '蔬菜']
const fieldUsersComputed = computed(() => userStore.usersRef.filter(
  (user) => user.capabilities.includes('upload_field_data'),
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
  ready: '位置已获取',
  creating: '正在创建记录',
  uploading_photo: '正在上传照片',
  pending_photo: '照片待补传',
  completed: '采集已完成',
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

watch(
  () => draftRef.value.observed_land_class,
  (landClass) => {
    if (landClass !== '耕地') draftRef.value.observed_crop_type = null
  },
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
  captureStore.setPhoto(file)
}

const captureLocation = async (): Promise<void> => {
  try {
    await captureStore.captureLocation()
    message.success('GPS 位置和终端精度已记录')
  } catch {
    message.warning(errorMessageRef.value || '无法获取 GPS 位置')
  }
}

const submit = async (): Promise<void> => {
  try {
    const result = await captureStore.submitCapture()
    if (result.completed) message.success('外业记录和现场照片已完成受控上传')
  } catch {
    if (pendingUploadRef.value) {
      message.warning('外业记录已创建，请保留或重新选择照片后补传')
    }
  }
}

const retryPhoto = async (): Promise<void> => {
  try {
    await captureStore.uploadPendingPhoto()
    message.success('现场照片补传成功，采集记录已完整')
  } catch {
    message.warning(errorMessageRef.value || '照片补传失败')
  }
}
</script>

<template>
  <main class="capture-card">
    <header class="capture-heading">
      <span class="heading-icon"><EnvironmentOutlined /></span>
      <span>
        <small>AGRISCOPE FIELD</small>
        <strong>移动外业核查采集</strong>
        <em>{{ taskCodeRef }} · GPS、现场属性与照片实体</em>
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
      description="表单草稿会保存在本机；恢复网络后才能创建记录和上传现场照片。"
    />
    <a-alert
      v-else-if="!secureContextRef"
      type="error"
      show-icon
      message="当前页面不是 HTTPS 安全连接"
      description="浏览器会阻止现场 GPS；请通过 HTTPS 网关打开移动采集页面。"
    />

    <section class="capture-section identity-section">
      <div class="section-title">
        <span><strong>采集身份</strong><small>权限由后端项目成员目录决定</small></span>
        <a-tag>{{ statusLabelComputed }}</a-tag>
      </div>
      <a-select
        :value="userStore.currentUserComputed?.user_code"
        :loading="userStore.loadingRef"
        placeholder="选择外业核查员"
        @change="(value: string) => userStore.setCurrentUser(value)"
      >
        <a-select-option
          v-for="user in fieldUsersComputed"
          :key="user.user_code"
          :value="user.user_code"
        >
          {{ user.display_name }} · {{ user.role_name }}
        </a-select-option>
      </a-select>
      <small class="audit-hint">
        当前稳定用户编码：{{ userStore.currentUserComputed?.user_code || '--' }}
      </small>
    </section>

    <section class="capture-section location-section">
      <div class="section-title">
        <span><strong>现场 GPS</strong><small>WGS84 坐标和终端水平精度写入数据库</small></span>
        <AimOutlined />
      </div>
      <div v-if="draftRef.lon !== null" class="location-grid">
        <div><small>经度</small><strong>{{ draftRef.lon.toFixed(6) }}</strong></div>
        <div><small>纬度</small><strong>{{ draftRef.lat?.toFixed(6) }}</strong></div>
        <div :class="['accuracy', accuracyStateComputed]"><small>定位精度</small><strong>± {{ draftRef.location_accuracy_m }} m</strong></div>
        <div><small>采集时间</small><strong>{{ draftRef.captured_at?.slice(0, 19).replace('T', ' ') }}</strong></div>
      </div>
      <a-button
        block
        type="primary"
        ghost
        :loading="statusRef === 'locating'"
        @click="captureLocation"
      >
        <template #icon><AimOutlined /></template>
        {{ draftRef.lon === null ? '获取当前 GPS 位置' : '重新定位' }}
      </a-button>
      <p v-if="draftRef.location_accuracy_m && draftRef.location_accuracy_m > 100" class="accuracy-warning">
        当前定位误差超过 100 米，建议移动到开阔位置后重新定位；服务端仍会保存真实精度，不会伪造高精度结果。
      </p>
    </section>

    <section class="capture-section">
      <div class="section-title">
        <span><strong>现场判定</strong><small>耕地必须填写现场作物</small></span>
      </div>
      <div class="field-grid">
        <label>
          <span>现场地类</span>
          <a-select v-model:value="draftRef.observed_land_class" placeholder="请选择">
            <a-select-option v-for="item in landClassOptions" :key="item" :value="item">
              {{ item }}
            </a-select-option>
          </a-select>
        </label>
        <label>
          <span>现场作物</span>
          <a-select
            v-model:value="draftRef.observed_crop_type"
            allow-clear
            :disabled="draftRef.observed_land_class !== '耕地'"
            placeholder="请选择"
          >
            <a-select-option v-for="item in cropTypeOptions" :key="item" :value="item">
              {{ item }}
            </a-select-option>
          </a-select>
        </label>
      </div>
      <label class="remark-field">
        <span>现场备注</span>
        <a-textarea
          v-model:value="draftRef.remark"
          :maxlength="1000"
          :auto-size="{ minRows: 3, maxRows: 6 }"
          placeholder="记录地表状况、边界标志、种植状态或异常情况"
        />
      </label>
    </section>

    <section class="capture-section photo-section">
      <div class="section-title">
        <span><strong>现场照片实体</strong><small>必须通过服务端签名、大小和 SHA-256 校验</small></span>
        <CameraOutlined />
      </div>
      <button class="photo-picker" type="button" @click="photoInputRef?.click()">
        <img v-if="photoPreviewUrlRef" :src="photoPreviewUrlRef" alt="待上传现场照片预览">
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
      v-if="pendingUploadRef"
      type="warning"
      show-icon
      message="外业记录已创建，现场照片尚未完成受控上传"
      :description="`记录 ${pendingUploadRef.verification_code} 已保留；重新选择同一照片后可安全重试，重复实体不会生成第二份证据。`"
    />
    <a-alert
      v-else-if="errorMessageRef"
      type="error"
      show-icon
      :message="errorMessageRef"
    />
    <a-alert
      v-if="resultRef?.completed"
      type="success"
      show-icon
      message="现场采集已完整入库"
      :description="`匹配状态 ${resultRef.record.match_status}；图斑 ${resultRef.record.matched_plot_code || '未匹配'}；照片 SHA-256 ${resultRef.artifact?.checksum_sha256 || '--'}`"
    />

    <div class="submit-bar">
      <a-button
        v-if="pendingUploadRef"
        type="primary"
        size="large"
        block
        :disabled="!onlineRef || !photoFileRef"
        :loading="statusRef === 'uploading_photo'"
        @click="retryPhoto"
      >
        <template #icon><CloudSyncOutlined /></template>
        补传现场照片
      </a-button>
      <a-button
        v-else
        type="primary"
        size="large"
        block
        :disabled="!canSubmitComputed"
        :loading="['creating', 'uploading_photo'].includes(statusRef)"
        @click="submit"
      >
        <template #icon><CheckCircleOutlined /></template>
        创建记录并上传照片
      </a-button>
      <a-button
        v-if="resultRef?.completed"
        block
        @click="captureStore.resetDraft()"
      >
        <template #icon><ReloadOutlined /></template>
        继续采集下一点
      </a-button>
    </div>
  </main>
</template>

<style scoped lang="less">
.capture-card { width: min(100%, 620px); padding: 16px; margin: 0 auto; }
.capture-heading { display: grid; grid-template-columns: 42px minmax(0, 1fr) auto; gap: 10px; align-items: center; padding: 16px; color: #fff; background: #11352a; border-radius: 16px; }
.capture-heading > span:not(.heading-icon) { display: flex; flex-direction: column; min-width: 0; }
.capture-heading small { font-size: 9px; letter-spacing: .12em; color: #8fc9aa; }
.capture-heading strong { margin-top: 2px; font-size: 18px; }
.capture-heading em { overflow: hidden; margin-top: 2px; font-size: 10px; font-style: normal; color: rgb(255 255 255 / 58%); text-overflow: ellipsis; white-space: nowrap; }
.heading-icon { display: grid; place-items: center; width: 42px; height: 42px; font-size: 20px; color: #d9b94f; background: rgb(255 255 255 / 8%); border: 1px solid rgb(255 255 255 / 12%); border-radius: 12px; }
.capture-card > .ant-alert { margin-top: 12px; }
.capture-section { padding: 14px; margin-top: 12px; background: #fff; border: 1px solid #dfe7e3; border-radius: 14px; }
.section-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; color: #315a49; }
.section-title > span { display: flex; flex-direction: column; }
.section-title strong { font-size: 13px; color: #20382e; }
.section-title small, .audit-hint { font-size: 9px; color: #82918a; }
.identity-section .ant-select { width: 100%; }
.audit-hint { display: block; margin-top: 6px; }
.location-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 10px; }
.location-grid > div { display: flex; flex-direction: column; padding: 9px; background: #f5f8f6; border-radius: 9px; }
.location-grid small { font-size: 9px; color: #839089; }
.location-grid strong { margin-top: 3px; font-size: 12px; }
.location-grid .accuracy.success strong { color: #31885e; }
.location-grid .accuracy.warning strong { color: #b16c1f; }
.location-grid .accuracy.error strong { color: #bf4545; }
.accuracy-warning { margin: 8px 0 0; font-size: 10px; line-height: 1.5; color: #a35f1b; }
.field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.field-grid label, .remark-field { display: flex; flex-direction: column; gap: 5px; font-size: 10px; color: #65736c; }
.remark-field { margin-top: 10px; }
.photo-picker { display: grid; place-items: center; width: 100%; min-height: 190px; padding: 0; overflow: hidden; color: #476758; cursor: pointer; background: #f1f6f3; border: 1px dashed #a8bdb2; border-radius: 12px; }
.photo-picker img { width: 100%; max-height: 320px; object-fit: cover; }
.photo-picker span { display: flex; flex-direction: column; align-items: center; gap: 5px; }
.photo-picker span > :first-child { font-size: 26px; }
.photo-picker small { font-size: 9px; color: #91a098; }
.hidden-file { display: none; }
.photo-meta { margin: 8px 0 0; font-size: 10px; color: #708078; }
.submit-bar { position: sticky; bottom: 0; display: grid; gap: 8px; padding: 12px 0 4px; background: linear-gradient(to bottom, transparent, #eef3f0 18%); }
@media (max-width: 520px) {
  .capture-card { padding: 10px; }
  .capture-heading { grid-template-columns: 38px minmax(0, 1fr); border-radius: 12px; }
  .capture-heading > .ant-tag { grid-column: 1 / -1; justify-self: start; }
  .field-grid { grid-template-columns: 1fr; }
}
</style>
