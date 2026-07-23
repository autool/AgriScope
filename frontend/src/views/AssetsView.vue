<script setup lang="ts">
import {
  CheckCircleOutlined,
  CloudUploadOutlined,
  DatabaseOutlined,
  FileImageOutlined,
  WarningOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref } from 'vue'

import ImageryBatchUploadModal from '@/components/imagery/ImageryBatchUploadModal.vue'
import { useAssetStore } from '@/store/assetStore'
import { useUserStore } from '@/store/userStore'
import type { ImageryBatchManifest } from '@/types/imageryBatch'
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
const selectedAssetCodeRef = ref<string | null>(null)

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

const openUpload = (): void => {
  uploadVisibleRef.value = true
}

const cancelUpload = (): void => {
  if (uploadingRef.value) return
  uploadVisibleRef.value = false
}

/**
 * 提交一个影像原子批次并选中新批次首个资产。
 * Args:
 *   files: 1–20 个保持原生 File 类型的实体文件。
 *   manifest: 与文件名逐一对应的批次清单。
 * Returns:
 *   Promise<void>: 批次入库和目录刷新完成后结束。
 */
const submitUpload = async (
  files: File[],
  manifest: Omit<ImageryBatchManifest, 'operator_code'>,
): Promise<void> => {
  try {
    const batch = await assetStore.uploadBatch(files, manifest)
    selectedAssetCodeRef.value = batch.items[0]?.asset_code || null
    uploadVisibleRef.value = false
    message.success(
      `批次 ${batch.batch_code} 已原子入库 ${batch.item_count} 景影像，清单 SHA256 ${batch.manifest_sha256.slice(0, 16)}…`,
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
        <CloudUploadOutlined /> 批量影像入库
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
            <div><dt>入库批次</dt><dd>{{ selectedAssetComputed.raster_metadata.import_batch_code || '--' }}</dd></div>
          </dl>
          <div class="checksum"><small>SHA256</small><code>{{ selectedAssetComputed.checksum_sha256 || '--' }}</code></div>
          <div class="checksum"><small>批次清单 SHA256</small><code>{{ selectedAssetComputed.raster_metadata.import_manifest_sha256 || '--' }}</code></div>
          <div class="footprint"><small>WGS84 覆盖范围</small><code>{{ footprintTextComputed }}</code></div>
        </aside>
      </div>
    </a-spin>

    <ImageryBatchUploadModal
      :open="uploadVisibleRef"
      :loading="uploadingRef"
      :progress="uploadProgressRef"
      :operator-name="userStore.currentUserComputed?.display_name || ''"
      :operator-role="userStore.currentUserComputed?.role_name || ''"
      @cancel="cancelUpload"
      @submit="submitUpload"
    />
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
@media (max-width: 1000px) {
  .asset-content { grid-template-columns: 1fr; }
}
</style>
