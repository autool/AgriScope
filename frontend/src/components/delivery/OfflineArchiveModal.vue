<script setup lang="ts">
import {
  CloudDownloadOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  HddOutlined,
  ReloadOutlined,
} from '@ant-design/icons-vue'
import { computed, ref, watch } from 'vue'

import type {
  OfflineArchive,
  OfflineArchiveOverview,
  OfflineArchiveVolume,
} from '@/types/offlineArchive'

const MEBIBYTE = 1024 * 1024

const props = defineProps<{
  open: boolean
  taskCode: string
  overview: OfflineArchiveOverview | null
  loading: boolean
  generating: boolean
  downloadingKey: string | null
  canGenerate: boolean
  canDownload: boolean
}>()

const emit = defineEmits<{
  cancel: []
  refresh: []
  generate: [payload: {
    archive_name: string | null
    volume_capacity_bytes: number
    comment: string
  }]
  downloadManifest: [archive: OfflineArchive]
  downloadVolume: [archive: OfflineArchive, volume: OfflineArchiveVolume]
}>()

const archiveNameRef = ref<string>('')
const capacityMiBRef = ref<number>(4096)
const commentRef = ref<string>('')

const maxCapacityMiBComputed = computed<number>(() => Math.floor(
  (props.overview?.max_volume_capacity_bytes || 16 * 1024 * MEBIBYTE)
  / MEBIBYTE,
))
const configuredCapacityBytesComputed = computed<number>(() => (
  Math.round(capacityMiBRef.value || 0) * MEBIBYTE
))
const estimatedVolumeCountComputed = computed<number>(() => {
  const total = props.overview?.total_source_bytes || 0
  const capacity = configuredCapacityBytesComputed.value
  if (!total || capacity <= 0) return 0
  return Math.max(1, Math.ceil(total / capacity))
})
const formErrorComputed = computed<string | null>(() => {
  if (capacityMiBRef.value < 64) return '单卷容量不得低于 64 MiB'
  if (capacityMiBRef.value > maxCapacityMiBComputed.value) {
    return `单卷容量不得超过 ${maxCapacityMiBComputed.value} MiB`
  }
  if ((commentRef.value || '').trim().length < 10) {
    return '请填写至少 10 个字符的离线封存生成依据'
  }
  return null
})
const generateDisabledComputed = computed<boolean>(() => (
  !props.canGenerate || Boolean(formErrorComputed.value)
))

const formatBytes = (value: number | null | undefined): string => {
  if (!value) return '0 B'
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
  let size = value
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size.toFixed(index === 0 ? 0 : 2)} ${units[index]}`
}

const sourceKindLabel = (kind: string): string => ({
  delivery_package: '当前成果包',
  imagery_source: '业务源影像',
  imagery_product: '处理产物',
  dataset_asset: '多源数据实体',
}[kind] || kind)

const archiveStatusLabel = (archive: OfflineArchive): string => {
  if (archive.is_current) return '当前有效'
  if (archive.status === 'superseded') return '历史替代'
  return '已失效'
}

const resetForm = (): void => {
  const recommended = props.overview?.recommended_volume_capacity_bytes
  capacityMiBRef.value = Math.round((recommended || 4 * 1024 * MEBIBYTE) / MEBIBYTE)
  archiveNameRef.value = ''
  commentRef.value = '按当前交付版本封存全部受控源栅格、处理产物和多源数据实体'
}

const handleGenerate = (): void => {
  if (generateDisabledComputed.value) return
  emit('generate', {
    archive_name: archiveNameRef.value.trim() || null,
    volume_capacity_bytes: configuredCapacityBytesComputed.value,
    comment: commentRef.value.trim(),
  })
}

watch(
  () => props.open,
  (open) => {
    if (open) resetForm()
  },
)
</script>

<template>
  <a-modal
    :open="open"
    width="1120px"
    :footer="null"
    title="源栅格离线介质封存"
    @cancel="emit('cancel')"
  >
    <div class="offline-archive-modal">
      <header class="archive-heading">
        <div>
          <small>OFFLINE RASTER PRESERVATION</small>
          <strong>{{ taskCode }}</strong>
          <span>ZIP64 独立分卷 · 顶层规范清单 · 逐文件 SHA-256</span>
        </div>
        <a-button :loading="loading" @click="emit('refresh')">
          <ReloadOutlined />刷新实体预估
        </a-button>
      </header>

      <a-alert
        :type="overview?.can_generate ? 'success' : 'warning'"
        show-icon
        :message="overview?.can_generate ? '当前来源满足离线封存条件' : '离线封存尚不可生成'"
        :description="overview?.generate_blocker || '生成前会重新校验当前成果包和每个受控实体。'"
      />

      <section class="source-metrics">
        <article>
          <DatabaseOutlined />
          <span><small>受控实体</small><strong>{{ overview?.source_count || 0 }}</strong></span>
        </article>
        <article>
          <HddOutlined />
          <span><small>源数据总量</small><strong>{{ formatBytes(overview?.total_source_bytes) }}</strong></span>
        </article>
        <article>
          <FileTextOutlined />
          <span><small>最大单文件</small><strong>{{ formatBytes(overview?.largest_source_bytes) }}</strong></span>
        </article>
        <article>
          <CloudDownloadOutlined />
          <span><small>预计分卷</small><strong>{{ estimatedVolumeCountComputed || '--' }}</strong></span>
        </article>
      </section>

      <section class="source-breakdown">
        <header><strong>当前来源容量</strong><small>仅统计已重新校验的物理实体</small></header>
        <div>
          <article
            v-for="item in overview?.source_summaries || []"
            :key="item.source_kind"
          >
            <span>{{ sourceKindLabel(item.source_kind) }}</span>
            <strong>{{ item.source_count }} 项</strong>
            <em>{{ formatBytes(item.file_size_bytes) }}</em>
          </article>
          <a-empty
            v-if="!(overview?.source_summaries.length)"
            :image="null"
            description="尚无可封存实体"
          />
        </div>
      </section>

      <section class="generation-form">
        <header>
          <div><small>NEW VERSION</small><strong>生成新离线封存版本</strong></div>
          <a-tag color="blue">单文件不截断</a-tag>
        </header>
        <div class="form-grid">
          <label>
            <span>封存名称（可选）</span>
            <a-input
              v-model:value="archiveNameRef"
              maxlength="200"
              placeholder="默认使用任务名称和版本号"
            />
          </label>
          <label>
            <span>单卷最大容量（MiB）</span>
            <a-input-number
              v-model:value="capacityMiBRef"
              :min="64"
              :max="maxCapacityMiBComputed"
              :step="64"
              :precision="0"
              style="width: 100%"
            />
          </label>
          <label class="comment-field">
            <span>生成依据</span>
            <a-textarea
              v-model:value="commentRef"
              :rows="2"
              :maxlength="500"
              show-count
            />
          </label>
        </div>
        <footer>
          <span>
            <small v-if="formErrorComputed" class="error">{{ formErrorComputed }}</small>
            <small v-else>
              服务端将按 {{ formatBytes(configuredCapacityBytesComputed) }} 容量规划，
              实际卷数以 ZIP64 写入结果为准。
            </small>
          </span>
          <a-button
            type="primary"
            :disabled="generateDisabledComputed"
            :loading="generating"
            @click="handleGenerate"
          >
            生成离线介质
          </a-button>
        </footer>
      </section>

      <section class="archive-history">
        <header>
          <div><small>VERSION HISTORY</small><strong>封存版本与独立分卷</strong></div>
          <span>{{ overview?.archives.length || 0 }} 个版本</span>
        </header>
        <a-empty
          v-if="!(overview?.archives.length)"
          description="尚未生成离线封存版本"
        />
        <article
          v-for="archive in overview?.archives || []"
          :key="archive.archive_code"
          class="archive-card"
          :class="{ stale: !archive.is_current }"
        >
          <header>
            <div>
              <i>V{{ archive.version }}</i>
              <span>
                <strong>{{ archive.archive_name }}</strong>
                <small>{{ archive.archive_code }}</small>
              </span>
            </div>
            <a-tag :color="archive.is_current ? 'green' : 'default'">
              {{ archiveStatusLabel(archive) }}
            </a-tag>
          </header>
          <a-alert
            v-if="archive.stale_reason"
            type="warning"
            show-icon
            :message="archive.stale_reason"
          />
          <div class="archive-meta">
            <span><small>实体</small><strong>{{ archive.source_count }} 项</strong></span>
            <span><small>源数据</small><strong>{{ formatBytes(archive.total_source_bytes) }}</strong></span>
            <span><small>介质总量</small><strong>{{ formatBytes(archive.total_archive_bytes) }}</strong></span>
            <span><small>分卷</small><strong>{{ archive.volume_count }} 卷</strong></span>
            <span><small>生成人</small><strong>{{ archive.generated_by }}</strong></span>
            <span><small>生成时间</small><strong>{{ new Date(archive.generated_at).toLocaleString('zh-CN') }}</strong></span>
          </div>
          <div class="volume-list">
            <div class="manifest-row">
              <span>
                <FileTextOutlined />
                <strong>顶层规范清单</strong>
                <small>SHA {{ archive.manifest_checksum_sha256.slice(0, 16) }}…</small>
              </span>
              <a-button
                size="small"
                :disabled="!canDownload || !archive.is_current"
                :loading="downloadingKey === `${archive.archive_code}:manifest`"
                @click="emit('downloadManifest', archive)"
              >
                下载清单
              </a-button>
            </div>
            <div
              v-for="volume in archive.volumes"
              :key="volume.sequence"
              class="volume-row"
            >
              <span>
                <HddOutlined />
                <strong>第 {{ volume.sequence }} 卷 · {{ volume.filename }}</strong>
                <small>
                  {{ volume.member_count }} 个实体 · {{ formatBytes(volume.file_size_bytes) }} ·
                  SHA {{ volume.checksum_sha256.slice(0, 16) }}…
                </small>
              </span>
              <a-button
                size="small"
                type="primary"
                ghost
                :disabled="!canDownload || !archive.is_current"
                :loading="downloadingKey === `${archive.archive_code}:${volume.sequence}`"
                @click="emit('downloadVolume', archive, volume)"
              >
                下载分卷
              </a-button>
            </div>
          </div>
          <footer>
            <span>来源快照 {{ archive.source_snapshot_sha256 }}</span>
            <em>{{ archive.generation_comment }}</em>
          </footer>
        </article>
      </section>
    </div>
  </a-modal>
</template>

<style scoped>
.offline-archive-modal { display: grid; gap: 12px; max-height: 76vh; overflow: auto; }
.archive-heading, .source-breakdown > header, .generation-form > header, .archive-history > header, .archive-card > header, .generation-form > footer { display: flex; align-items: center; justify-content: space-between; }
.archive-heading > div, .generation-form header > div, .archive-history header > div { display: flex; flex-direction: column; }
.archive-heading small, .generation-form header small, .archive-history header small { font-size: 9px; color: #87958e; letter-spacing: .08em; }
.archive-heading strong { font-size: 17px; color: #254f3c; }
.archive-heading span { font-size: 11px; color: #75837c; }
.source-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.source-metrics article { display: flex; gap: 10px; align-items: center; padding: 13px; background: #f5f8f6; border: 1px solid #e1e8e4; border-radius: 7px; }
.source-metrics article > :first-child { font-size: 21px; color: #3d8b63; }
.source-metrics span { display: flex; flex-direction: column; }
.source-metrics small, .archive-meta small { font-size: 9px; color: #7d8b84; }
.source-metrics strong { font-size: 17px; color: #2d5f47; }
.source-breakdown, .generation-form, .archive-history { padding: 13px; border: 1px solid #e0e7e3; border-radius: 7px; }
.source-breakdown header small, .archive-history > header > span { font-size: 10px; color: #7d8983; }
.source-breakdown > div { display: grid; grid-template-columns: repeat(4, 1fr); gap: 7px; margin-top: 9px; }
.source-breakdown article { display: grid; grid-template-columns: 1fr auto; gap: 3px 8px; padding: 9px; background: #f7f9f8; border-radius: 5px; }
.source-breakdown article span { font-size: 10px; color: #53635b; }
.source-breakdown article strong { font-size: 10px; color: #2f694c; }
.source-breakdown article em { grid-column: 1 / -1; font-size: 9px; font-style: normal; color: #88958f; }
.form-grid { display: grid; grid-template-columns: 1.4fr .8fr; gap: 10px; margin-top: 10px; }
.form-grid label { display: flex; flex-direction: column; gap: 5px; }
.form-grid label > span { font-size: 10px; color: #526159; }
.comment-field { grid-column: 1 / -1; }
.generation-form > footer { margin-top: 9px; }
.generation-form footer small { font-size: 10px; color: #718078; }
.generation-form footer .error { color: #c04444; }
.archive-history { display: grid; gap: 9px; }
.archive-card { padding: 11px; background: #fbfcfb; border: 1px solid #dce6e0; border-radius: 7px; }
.archive-card.stale { background: #f7f7f7; border-color: #e4e4e4; }
.archive-card > header > div { display: flex; gap: 8px; align-items: center; }
.archive-card header i { display: grid; width: 34px; height: 34px; font-size: 10px; font-style: normal; color: #2f7451; background: #e5f1ea; border-radius: 50%; place-items: center; }
.archive-card header span { display: flex; flex-direction: column; }
.archive-card header strong { font-size: 11px; color: #34463d; }
.archive-card header small { font-size: 9px; color: #849089; }
.archive-card :deep(.ant-alert) { margin-top: 8px; }
.archive-meta { display: grid; grid-template-columns: repeat(6, 1fr); gap: 7px; margin: 9px 0; }
.archive-meta span { display: flex; flex-direction: column; padding: 7px; background: #f2f6f4; border-radius: 4px; }
.archive-meta strong { overflow: hidden; font-size: 10px; color: #41544a; text-overflow: ellipsis; white-space: nowrap; }
.volume-list { display: grid; gap: 5px; }
.manifest-row, .volume-row { display: flex; align-items: center; justify-content: space-between; padding: 8px; background: #fff; border: 1px solid #e5ebe8; border-radius: 5px; }
.manifest-row > span, .volume-row > span { display: grid; grid-template-columns: 22px 1fr; align-items: center; min-width: 0; }
.manifest-row span > :first-child, .volume-row span > :first-child { grid-row: 1 / 3; color: #3b825d; }
.manifest-row strong, .volume-row strong { overflow: hidden; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.manifest-row small, .volume-row small { overflow: hidden; font-size: 9px; color: #85918b; text-overflow: ellipsis; white-space: nowrap; }
.archive-card > footer { display: grid; gap: 2px; margin-top: 8px; }
.archive-card > footer span { overflow: hidden; font-family: monospace; font-size: 8px; color: #87948d; text-overflow: ellipsis; white-space: nowrap; }
.archive-card > footer em { font-size: 9px; font-style: normal; color: #68766f; }
@media (max-width: 900px) {
  .source-metrics, .source-breakdown > div { grid-template-columns: repeat(2, 1fr); }
  .archive-meta { grid-template-columns: repeat(3, 1fr); }
}
</style>
