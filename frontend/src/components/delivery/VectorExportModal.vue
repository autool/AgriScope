<script setup lang="ts">
import {
  CloudDownloadOutlined,
  DatabaseOutlined,
  ReloadOutlined,
} from '@ant-design/icons-vue'
import { computed, ref, watch } from 'vue'

import type {
  VectorExportFormat,
  VectorExportOptions,
  VectorExportPackage,
  VectorLandClass,
} from '@/types/vectorExport'

const props = defineProps<{
  open: boolean
  taskCode: string
  options: VectorExportOptions | null
  items: VectorExportPackage[]
  generating: boolean
  loading: boolean
  downloadingCode: string | null
  canGenerate: boolean
  canDownload: boolean
}>()

const emit = defineEmits<{
  cancel: []
  refresh: []
  generate: [payload: {
    export_title: string
    formats: VectorExportFormat[]
    district_codes: string[]
    land_classes: VectorLandClass[]
    comment: string
  }]
  download: [item: VectorExportPackage]
}>()

const exportTitleRef = ref<string>('')
const formatsRef = ref<VectorExportFormat[]>([
  'geojson',
  'shapefile',
  'kml',
  'filegdb',
])
const districtCodesRef = ref<string[]>([])
const landClassesRef = ref<VectorLandClass[]>([])
const commentRef = ref<string>('')

const formatOptions = [
  { label: 'GeoJSON', value: 'geojson' },
  { label: 'Shapefile', value: 'shapefile' },
  { label: 'KML', value: 'kml' },
  { label: 'FileGDB', value: 'filegdb' },
]

const districtOptionsComputed = computed(() => (
  props.options?.districts.map((item) => ({
    value: item.code || '',
    label: `${item.parent_label || '未归属'} · ${item.label}（${item.feature_count}）`,
  })) || []
))
const landClassOptionsComputed = computed(() => (
  props.options?.land_classes.map((item) => ({
    value: item.label,
    label: `${item.label}（${item.feature_count}）`,
  })) || []
))
const estimatedCountComputed = computed<string>(() => {
  if (!props.options) return '--'
  if (!districtCodesRef.value.length && !landClassesRef.value.length) {
    return `${props.options.total_feature_count} 个`
  }
  if (districtCodesRef.value.length && !landClassesRef.value.length) {
    const count = props.options.districts
      .filter((item) => item.code && districtCodesRef.value.includes(item.code))
      .reduce((total, item) => total + item.feature_count, 0)
    return `${count} 个`
  }
  if (!districtCodesRef.value.length && landClassesRef.value.length) {
    const count = props.options.land_classes
      .filter((item) => landClassesRef.value.includes(item.label as VectorLandClass))
      .reduce((total, item) => total + item.feature_count, 0)
    return `${count} 个`
  }
  return '由服务端按县区与地类交集精确计算'
})
const canSubmitComputed = computed<boolean>(() => (
  props.canGenerate
  && formatsRef.value.length > 0
  && exportTitleRef.value.trim().length >= 2
  && commentRef.value.trim().length >= 4
  && !props.generating
))

const formatBytes = (value: number): string => {
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(2)} MB`
  return `${(value / 1024).toFixed(2)} KB`
}

const statusLabel = (item: VectorExportPackage): string => {
  if (item.status === 'invalid') return '实体无效'
  return item.is_current ? '当前成果' : '历史版本'
}

const statusColor = (item: VectorExportPackage): string => {
  if (item.status === 'invalid') return 'red'
  return item.is_current ? 'green' : 'default'
}

const submit = (): void => {
  if (!canSubmitComputed.value) return
  emit('generate', {
    export_title: exportTitleRef.value.trim(),
    formats: formatsRef.value,
    district_codes: districtCodesRef.value,
    land_classes: landClassesRef.value,
    comment: commentRef.value.trim(),
  })
}

watch(
  () => props.open,
  (open) => {
    if (!open) return
    exportTitleRef.value ||= `${props.taskCode} 农业遥感矢量成果`
    commentRef.value ||= '依据当前任务显式图斑范围生成，用于成果交换、复核和归档。'
  },
  { immediate: true },
)
</script>

<template>
  <a-modal
    :open="open"
    title="多格式矢量成果导出"
    width="980px"
    :footer="null"
    @cancel="emit('cancel')"
  >
    <a-alert
      type="info"
      show-icon
      message="真实格式生成与实体复核"
      description="GeoJSON、ESRI Shapefile、OGC KML 和 OpenFileGDB 均由服务端真实创建并重新打开验证；ZIP 保存逐文件 SHA-256、任务版本、县区/地类筛选和稳定用户审计。"
    />

    <section class="export-form">
      <header>
        <span><DatabaseOutlined /><strong>生成新版本</strong><small>{{ taskCode }}</small></span>
        <a-tag :color="canGenerate ? 'green' : 'default'">
          {{ canGenerate ? '项目负责人可生成' : '当前身份只读' }}
        </a-tag>
      </header>
      <label>
        <span>成果标题</span>
        <a-input v-model:value="exportTitleRef" :maxlength="80" :disabled="!canGenerate" />
      </label>
      <label>
        <span>输出格式</span>
        <a-checkbox-group
          v-model:value="formatsRef"
          :options="formatOptions"
          :disabled="!canGenerate"
        />
      </label>
      <div class="filter-grid">
        <label>
          <span>县区筛选（不选表示全部）</span>
          <a-select
            v-model:value="districtCodesRef"
            mode="multiple"
            show-search
            allow-clear
            :max-tag-count="3"
            :options="districtOptionsComputed"
            :disabled="!canGenerate"
            placeholder="全部 122 个县区"
          />
        </label>
        <label>
          <span>一级地类（不选表示全部）</span>
          <a-select
            v-model:value="landClassesRef"
            mode="multiple"
            allow-clear
            :options="landClassOptionsComputed"
            :disabled="!canGenerate"
            placeholder="全部地类"
          />
        </label>
      </div>
      <label>
        <span>生成依据</span>
        <a-textarea
          v-model:value="commentRef"
          :rows="3"
          :maxlength="500"
          show-count
          :disabled="!canGenerate"
        />
      </label>
      <div class="export-gate">
        <span>
          预计范围：<b>{{ estimatedCountComputed }}</b>；单包上限
          {{ options?.max_feature_count || '--' }} 个。Shapefile 使用十字符兼容字段，完整字段保留在其他格式。
        </span>
        <a-button
          type="primary"
          :disabled="!canSubmitComputed"
          :loading="generating"
          @click="submit"
        >
          生成矢量成果包
        </a-button>
      </div>
    </section>

    <section class="export-history">
      <header>
        <span><strong>导出版本历史</strong><small>{{ items.length }} 个版本</small></span>
        <a-button size="small" :loading="loading" @click="emit('refresh')">
          <ReloadOutlined />刷新
        </a-button>
      </header>
      <div v-if="items.length" class="export-list">
        <article v-for="item in items" :key="item.export_code">
          <div>
            <span>
              <a-tag :color="statusColor(item)">{{ statusLabel(item) }}</a-tag>
              <b>V{{ item.version }} · {{ item.export_title }}</b>
            </span>
            <small>{{ item.export_code }}</small>
            <p>
              {{ item.feature_count }} 个图斑 · {{ item.formats.join(' / ') }} ·
              {{ new Date(item.generated_at).toLocaleString('zh-CN') }} ·
              {{ item.generated_by }}
            </p>
            <em>
              县区 {{ item.district_codes.length || '全部' }} ·
              地类 {{ item.land_classes.length ? item.land_classes.join('、') : '全部' }} ·
              {{ formatBytes(item.file_size_bytes) }}
            </em>
            <code :title="item.checksum_sha256">SHA-256 {{ item.checksum_sha256 }}</code>
            <a-alert
              v-if="item.stale_reason"
              class="stale-alert"
              :type="item.status === 'invalid' ? 'error' : 'warning'"
              show-icon
              :message="item.stale_reason"
            />
          </div>
          <a-tooltip :title="canDownload ? '下载并重新校验全部格式' : '仅项目负责人和甲方可下载'">
            <a-button
              :disabled="!canDownload || !item.download_url"
              :loading="downloadingCode === item.export_code"
              @click="emit('download', item)"
            >
              <CloudDownloadOutlined />下载 ZIP
            </a-button>
          </a-tooltip>
        </article>
      </div>
      <a-empty v-else description="尚未生成多格式矢量成果" />
    </section>
  </a-modal>
</template>

<style scoped>
.export-form,
.export-history { padding: 14px; margin-top: 14px; background: #fbfcfb; border: 1px solid #dfe6e2; border-radius: 7px; }
.export-form > header,
.export-history > header,
.export-gate,
.export-list article,
.export-form header > span,
.export-history header > span,
.export-list article > div > span { display: flex; align-items: center; }
.export-form > header,
.export-history > header,
.export-gate,
.export-list article { justify-content: space-between; }
.export-form > header,
.export-history > header { margin-bottom: 10px; }
.export-form header > span,
.export-history header > span { gap: 7px; }
.export-form header small,
.export-history header small { color: #7d8a83; }
.export-form > label,
.filter-grid label { display: grid; gap: 5px; margin-top: 10px; font-size: 12px; }
.filter-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.export-gate { gap: 16px; margin-top: 12px; }
.export-gate > span { font-size: 11px; color: #68776f; }
.export-list { display: grid; gap: 9px; }
.export-list article { gap: 16px; padding: 12px; background: #fff; border: 1px solid #e1e8e4; border-radius: 6px; }
.export-list article > div { min-width: 0; flex: 1; }
.export-list article > div > span { gap: 6px; }
.export-list b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.export-list small,
.export-list p,
.export-list em,
.export-list code { display: block; margin-top: 5px; font-size: 11px; }
.export-list small,
.export-list p,
.export-list em { color: #78867e; }
.export-list p { margin-bottom: 0; }
.export-list em { font-style: normal; }
.export-list code { overflow: hidden; color: #66756d; text-overflow: ellipsis; white-space: nowrap; }
.stale-alert { margin-top: 8px; }
@media (max-width: 900px) { .filter-grid { grid-template-columns: 1fr; } }
</style>
