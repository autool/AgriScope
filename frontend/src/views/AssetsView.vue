<script setup lang="ts">
import {
  CheckCircleOutlined,
  CloudUploadOutlined,
  DatabaseOutlined,
  FileImageOutlined,
  WarningOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import type { UploadProps } from 'ant-design-vue'
import type { Dayjs } from 'dayjs'
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref, shallowRef } from 'vue'

import { useAssetStore } from '@/store/assetStore'
import { useUserStore } from '@/store/userStore'
import type {
  ImageryAssetItem,
  ImageryBusinessMetadataField,
} from '@/types/workbench'

const assetStore = useAssetStore()
const userStore = useUserStore()
const {
  canManageComputed,
  catalogRef,
  loadingRef,
  uploadingRef,
  uploadProgressRef,
} = storeToRefs(assetStore)
const uploadVisibleRef = ref<boolean>(false)
// File/RcFile 必须保持原生对象，避免深层响应式代理导致浏览器上传流失效。
const selectedFileRef = shallowRef<File | null>(null)
const selectedAssetCodeRef = ref<string | null>(null)
const assetCodeRef = ref<string>('')
const assetNameRef = ref<string>('')
const sensorTypeRef = ref<string>('')
const acquiredAtRef = ref<Dayjs | null>(null)
const cloudCoverRef = ref<number | null>(null)
const processingLevelRef = ref<string>('')
const dataStatusRef = ref<'operational' | 'demo'>('operational')

const selectedAssetComputed = computed<ImageryAssetItem | null>(() => (
  catalogRef.value?.items.find(
    (item) => item.asset_code === selectedAssetCodeRef.value,
  ) || catalogRef.value?.items[0] || null
))
const footprintTextComputed = computed<string>(() => (
  selectedAssetComputed.value?.footprint
    ? JSON.stringify(selectedAssetComputed.value.footprint.coordinates)
    : '--'
))
const businessMetadataComputed = computed(() => (
  selectedAssetComputed.value?.raster_metadata.business_metadata || {}
))

const metadataSourceLabel = (
  field: ImageryBusinessMetadataField | undefined,
): string => {
  if (!field) return '历史记录未保存来源'
  if (field.source === 'user_fallback') return '人工补录（文件标签缺失）'
  if (field.source === 'missing') return '文件与人工均未提供'
  if (field.source.startsWith('user_refinement:')) {
    return `文件标签 ${field.raster_tag || '--'} + 人工精确补充`
  }
  if (field.source.startsWith('raster_tag:')) {
    return `文件标签 ${field.raster_tag || '--'}`
  }
  return field.source
}

const formatBytes = (size: number | null): string => {
  if (size === null) return '--'
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  if (size < 1024 * 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  return `${(size / 1024 / 1024 / 1024).toFixed(2)} GB`
}

const beforeUpload: UploadProps['beforeUpload'] = (file) => {
  selectedFileRef.value = file
  const baseName = file.name.replace(/\.[^.]+$/, '')
  assetNameRef.value ||= baseName
  assetCodeRef.value ||= baseName
    .replace(/[^A-Za-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .toUpperCase()
    .slice(0, 80)
  return false
}

const resetUploadForm = (): void => {
  selectedFileRef.value = null
  assetCodeRef.value = ''
  assetNameRef.value = ''
  sensorTypeRef.value = ''
  acquiredAtRef.value = null
  cloudCoverRef.value = null
  processingLevelRef.value = ''
  dataStatusRef.value = 'operational'
}

const openUpload = (): void => {
  resetUploadForm()
  uploadVisibleRef.value = true
}

const cancelUpload = (): void => {
  uploadVisibleRef.value = false
  resetUploadForm()
}

/**
 * 上传影像文件并使用后端 Rasterio 解析结果刷新目录。
 * Args:
 *   无。
 * Returns:
 *   Promise<void>: 文件上传和目录刷新完成后结束。
 */
const submitUpload = async (): Promise<void> => {
  if (!selectedFileRef.value) {
    message.warning('请选择 GeoTIFF、IMG 或 HDF 文件')
    return
  }
  if (
    !assetCodeRef.value
    || !assetNameRef.value
  ) {
    message.warning('请填写资产编号和资产名称')
    return
  }
  try {
    const asset = await assetStore.upload(selectedFileRef.value, {
      assetCode: assetCodeRef.value.trim(),
      assetName: assetNameRef.value.trim(),
      sensorType: sensorTypeRef.value.trim() || null,
      acquiredAt: acquiredAtRef.value?.toISOString() || null,
      cloudCover: cloudCoverRef.value,
      processingLevel: processingLevelRef.value.trim() || null,
      dataStatus: dataStatusRef.value,
    })
    selectedAssetCodeRef.value = asset.asset_code
    uploadVisibleRef.value = false
    resetUploadForm()
    message.success(
      `影像 ${asset.asset_code} 已入库：${asset.sensor_type} · ${asset.acquired_at.slice(0, 10)} · ${asset.band_count} 波段`,
    )
  } catch {
    // 请求拦截器已显示安全错误，避免组件事件产生未捕获 Promise。
  }
}

onMounted(() => {
  void assetStore.load()
})
</script>

<template>
  <div class="asset-view">
    <header class="asset-heading">
      <span><DatabaseOutlined /><i><small>DATA CATALOG</small><strong>真实影像资产目录</strong></i></span>
      <a-button
        type="primary"
        :disabled="!canManageComputed"
        title="仅内业解译员或项目负责人可导入影像"
        @click="openUpload"
      >
        <CloudUploadOutlined /> 影像入库
      </a-button>
    </header>

    <div class="asset-metrics">
      <article><DatabaseOutlined /><span><strong>{{ catalogRef?.total ?? 0 }}</strong><small>影像资产</small></span></article>
      <article class="success"><CheckCircleOutlined /><span><strong>{{ catalogRef?.available ?? 0 }}</strong><small>实体文件可用</small></span></article>
      <article class="warning"><WarningOutlined /><span><strong>{{ catalogRef?.metadata_only ?? 0 }}</strong><small>仅元数据/文件缺失</small></span></article>
    </div>

    <a-spin :spinning="loadingRef">
      <div class="asset-content">
        <section class="asset-list">
          <a-empty v-if="!catalogRef?.items.length" description="尚未导入影像资产" />
          <button
            v-for="item in catalogRef?.items || []"
            :key="item.asset_code"
            :class="{ active: selectedAssetComputed?.asset_code === item.asset_code }"
            @click="selectedAssetCodeRef = item.asset_code"
          >
            <FileImageOutlined />
            <span>
              <strong>{{ item.asset_name }}</strong>
              <small>{{ item.asset_code }} · {{ item.sensor_type }}</small>
              <em>{{ item.acquired_at.slice(0, 10) }} · {{ item.band_count ?? '--' }} 波段 · {{ formatBytes(item.file_size_bytes) }} · {{ item.data_status === 'demo' ? '明确演示' : '业务数据' }}</em>
            </span>
            <a-tag :color="item.file_verified ? 'green' : 'orange'">
              {{ item.file_verified ? '文件可用' : '仅元数据' }}
            </a-tag>
          </button>
        </section>

        <aside v-if="selectedAssetComputed" class="asset-detail">
          <header><span><small>ASSET DETAIL</small><strong>{{ selectedAssetComputed.asset_code }}</strong></span><a-tag :color="selectedAssetComputed.file_verified ? 'green' : 'orange'">{{ selectedAssetComputed.file_verified ? '已校验' : '不可用' }}</a-tag></header>
          <a-alert
            v-if="selectedAssetComputed.file_error"
            type="warning"
            show-icon
            :message="selectedAssetComputed.file_error"
          />
          <dl>
            <div class="business-field">
              <dt>传感器</dt>
              <dd>
                <strong>{{ selectedAssetComputed.sensor_type }}</strong>
                <small>{{ metadataSourceLabel(businessMetadataComputed.sensor_type) }}</small>
              </dd>
            </div>
            <div class="business-field">
              <dt>采集时间</dt>
              <dd>
                <strong>{{ selectedAssetComputed.acquired_at.replace('T', ' ').slice(0, 19) }}</strong>
                <small>{{ metadataSourceLabel(businessMetadataComputed.acquired_at) }}</small>
              </dd>
            </div>
            <div class="business-field">
              <dt>处理级别</dt>
              <dd>
                <strong>{{ selectedAssetComputed.processing_level || '--' }}</strong>
                <small>{{ metadataSourceLabel(businessMetadataComputed.processing_level) }}</small>
              </dd>
            </div>
            <div class="business-field">
              <dt>云量</dt>
              <dd>
                <strong>{{ selectedAssetComputed.cloud_cover ?? '--' }}<template v-if="selectedAssetComputed.cloud_cover !== null">%</template></strong>
                <small>{{ metadataSourceLabel(businessMetadataComputed.cloud_cover) }}</small>
              </dd>
            </div>
            <div><dt>原始文件</dt><dd>{{ selectedAssetComputed.original_filename || '--' }}</dd></div>
            <div><dt>驱动格式</dt><dd>{{ selectedAssetComputed.file_format || '--' }}</dd></div>
            <div><dt>CRS</dt><dd>{{ selectedAssetComputed.crs || '--' }}</dd></div>
            <div><dt>栅格尺寸</dt><dd>{{ selectedAssetComputed.raster_width ?? '--' }} × {{ selectedAssetComputed.raster_height ?? '--' }}</dd></div>
            <div><dt>波段数量</dt><dd>{{ selectedAssetComputed.band_count ?? '--' }}</dd></div>
            <div><dt>分辨率</dt><dd>{{ selectedAssetComputed.resolution_m ?? '--' }} m</dd></div>
            <div><dt>文件大小</dt><dd>{{ formatBytes(selectedAssetComputed.file_size_bytes) }}</dd></div>
            <div><dt>入库人员</dt><dd>{{ selectedAssetComputed.imported_by || '--' }}</dd></div>
          </dl>
          <div class="checksum"><small>SHA256</small><code>{{ selectedAssetComputed.checksum_sha256 || '--' }}</code></div>
          <div class="footprint"><small>WGS84 覆盖范围</small><code>{{ footprintTextComputed }}</code></div>
        </aside>
      </div>
    </a-spin>

    <a-modal
      v-model:open="uploadVisibleRef"
      title="遥感影像文件入库"
      width="640px"
      destroy-on-close
      :confirm-loading="uploadingRef"
      ok-text="上传并读取元数据"
      cancel-text="取消"
      @ok="submitUpload"
      @cancel="cancelUpload"
    >
      <a-alert
        type="info"
        show-icon
        message="业务元数据优先读取文件标签"
        description="支持 GeoTIFF、IMG、HDF。后端自动读取传感器、采集时间、处理级别、云量及空间元数据；文件缺失时才使用人工补录，二者冲突将拒绝入库。"
      />
      <div class="upload-form">
        <label class="file-row"><span>影像文件</span><a-upload :before-upload="beforeUpload" :max-count="1" :show-upload-list="true"><a-button><CloudUploadOutlined /> 选择文件</a-button></a-upload></label>
        <label><span>资产编号</span><a-input v-model:value="assetCodeRef" placeholder="仅允许字母、数字、下划线和连字符" /></label>
        <label><span>资产名称</span><a-input v-model:value="assetNameRef" placeholder="使用影像成果正式名称" /></label>
        <label><span>传感器补录</span><a-input v-model:value="sensorTypeRef" placeholder="文件标签缺失时填写" /></label>
        <label><span>时间补录</span><a-date-picker v-model:value="acquiredAtRef" show-time placeholder="文件缺失或仅含日期时填写" /></label>
        <label>
          <span>云量补录</span>
          <a-input-number
            v-model:value="cloudCoverRef"
            :min="0"
            :max="100"
            addon-after="%"
          />
        </label>
        <label><span>级别补录</span><a-input v-model:value="processingLevelRef" placeholder="文件标签缺失时填写" /></label>
        <label><span>数据属性</span><a-select v-model:value="dataStatusRef"><a-select-option value="operational">业务数据</a-select-option><a-select-option value="demo">明确演示数据</a-select-option></a-select></label>
        <label>
          <span>操作身份</span>
          <strong>{{ userStore.currentUserComputed?.display_name || '--' }} · {{ userStore.currentUserComputed?.role_name || '--' }}</strong>
        </label>
      </div>
      <a-progress v-if="uploadingRef" :percent="uploadProgressRef" />
    </a-modal>
  </div>
</template>

<style scoped>
.asset-view { height: 100%; padding: 14px; overflow: auto; background: #f2f5f3; }
.asset-heading, .asset-heading > span, .asset-heading i, .asset-metrics article, .asset-list button, .asset-detail > header { display: flex; align-items: center; }
.asset-heading { justify-content: space-between; padding: 14px 16px; background: #fff; border: 1px solid #dfe6e2; border-radius: 8px; }
.asset-heading > span { gap: 10px; color: #3d865f; }
.asset-heading > span > :first-child { font-size: 24px; }
.asset-heading i { flex-direction: column; align-items: flex-start; font-style: normal; }
small { font-size: 8px; color: #89958f; }
.asset-heading strong { font-size: 14px; color: #28362f; }
.asset-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 10px 0; }
.asset-metrics article { gap: 10px; padding: 12px 14px; color: #477e61; background: #fff; border: 1px solid #dfe6e2; border-radius: 7px; }
.asset-metrics article > :first-child { font-size: 20px; }
.asset-metrics span { display: flex; flex-direction: column; }
.asset-metrics strong { font-size: 18px; }
.asset-metrics .success { color: #34865b; }
.asset-metrics .warning { color: #c47d2c; }
.asset-content { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 10px; min-height: 480px; }
.asset-list, .asset-detail { padding: 12px; background: #fff; border: 1px solid #dfe6e2; border-radius: 8px; }
.asset-list button { display: grid; grid-template-columns: 32px minmax(0, 1fr) auto; gap: 10px; width: 100%; padding: 12px; text-align: left; background: #fff; border: 0; border-bottom: 1px solid #edf0ee; }
.asset-list button.active { background: #eff6f1; border-radius: 6px; }
.asset-list button > :first-child { font-size: 22px; color: #438664; }
.asset-list button span { display: flex; flex-direction: column; min-width: 0; }
.asset-list button strong { overflow: hidden; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.asset-list button em { margin-top: 3px; font-size: 8px; font-style: normal; color: #78847e; }
.asset-detail > header { justify-content: space-between; margin-bottom: 10px; }
.asset-detail > header span { display: flex; flex-direction: column; }
.asset-detail dl > div { display: flex; justify-content: space-between; padding: 8px 0; font-size: 9px; border-bottom: 1px dashed #e3e8e5; }
.asset-detail dd { max-width: 210px; margin: 0; overflow: hidden; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.asset-detail .business-field dd { display: flex; align-items: flex-end; flex-direction: column; }
.asset-detail .business-field dd strong { max-width: 210px; overflow: hidden; text-overflow: ellipsis; }
.asset-detail .business-field dd small { margin-top: 2px; font-weight: 400; color: #4c8062; }
.checksum, .footprint { padding: 10px; margin-top: 10px; background: #f6f8f7; border-radius: 5px; }
.checksum code, .footprint code { display: block; margin-top: 4px; overflow: auto; font-size: 8px; overflow-wrap: anywhere; white-space: normal; }
.upload-form { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 14px; }
.upload-form label { display: grid; grid-template-columns: 80px minmax(0, 1fr); gap: 8px; align-items: center; font-size: 9px; }
.upload-form .file-row { grid-column: 1 / -1; }
.upload-form :deep(.ant-picker), .upload-form :deep(.ant-input-number) { width: 100%; }
@media (max-width: 1000px) {
  .asset-content { grid-template-columns: 1fr; }
  .upload-form { grid-template-columns: 1fr; }
  .upload-form .file-row { grid-column: auto; }
}
</style>
