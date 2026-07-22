<script setup lang="ts">
import {
  CloudDownloadOutlined,
  FileExcelOutlined,
  FilePdfOutlined,
  ReloadOutlined,
} from '@ant-design/icons-vue'
import { computed, ref, watch } from 'vue'

import type { StatisticsReport } from '@/types/workbench'

const props = defineProps<{
  open: boolean
  taskCode: string
  monitorYear: number | null
  reports: StatisticsReport[]
  generating: boolean
  downloadingCode: string | null
  canGenerate: boolean
  canDownload: boolean
}>()

const emit = defineEmits<{
  cancel: []
  generate: [reportTitle: string, comment: string]
  download: [report: StatisticsReport]
  refresh: []
}>()

const reportTitleRef = ref<string>('')
const commentRef = ref<string>('')
const canSubmitComputed = computed<boolean>(() => (
  props.canGenerate
  && reportTitleRef.value.trim().length >= 2
  && commentRef.value.trim().length >= 4
  && !props.generating
))

const formatBytes = (value: number): string => {
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(2)} MB`
  return `${(value / 1024).toFixed(2)} KB`
}

const formatTime = (value: string): string => new Date(value).toLocaleString('zh-CN')

const statusLabel = (report: StatisticsReport): string => {
  if (report.status === 'invalid') return '实体无效'
  if (report.is_current) return '当前正式版'
  return '历史版本'
}

const statusColor = (report: StatisticsReport): string => {
  if (report.status === 'invalid') return 'red'
  if (report.is_current) return 'green'
  return 'default'
}

watch(
  () => [props.open, props.monitorYear] as const,
  ([open, monitorYear]) => {
    if (!open) return
    reportTitleRef.value ||= `黑龙江省${monitorYear || ''}年度农作物种植面积监测统计报告`
    commentRef.value ||= '依据当前任务有效图斑和已入库真实历史年度快照生成正式统计成果。'
  },
  { immediate: true },
)
</script>

<template>
  <a-modal
    :open="open"
    title="面积统计正式报告"
    width="920px"
    :footer="null"
    @cancel="emit('cancel')"
  >
    <a-alert
      type="info"
      show-icon
      message="报告由服务端生成并持久化"
      description="每个版本原子包含 XLSX、PDF 和 manifest.json，保存内外文件大小、SHA-256、任务图斑数和历史快照状态；来源数据变化后自动转为历史版本。"
    />

    <section class="generate-section">
      <header>
        <div>
          <strong>生成新版本</strong>
          <small>{{ taskCode }} · {{ monitorYear || '--' }} 年</small>
        </div>
        <a-tag :color="canGenerate ? 'green' : 'default'">
          {{ canGenerate ? '项目负责人可生成' : '当前身份只读' }}
        </a-tag>
      </header>
      <a-input
        v-model:value="reportTitleRef"
        :maxlength="80"
        placeholder="正式报告标题"
        :disabled="!canGenerate"
      />
      <a-textarea
        v-model:value="commentRef"
        :rows="3"
        :maxlength="500"
        show-count
        placeholder="填写统计口径、数据版本或生成依据"
        :disabled="!canGenerate"
      />
      <div class="generate-actions">
        <span>输出：XLSX 多维统计与图表、PDF 标准报告、JSON 校验清单</span>
        <a-button
          type="primary"
          :disabled="!canSubmitComputed"
          :loading="generating"
          @click="emit('generate', reportTitleRef.trim(), commentRef.trim())"
        >
          生成正式报告包
        </a-button>
      </div>
    </section>

    <section class="history-section">
      <header>
        <div>
          <strong>报告版本历史</strong>
          <small>{{ reports.length }} 个受控版本</small>
        </div>
        <a-button size="small" :loading="generating" @click="emit('refresh')">
          <ReloadOutlined />刷新
        </a-button>
      </header>
      <div v-if="reports.length" class="report-list">
        <article v-for="report in reports" :key="report.report_code">
          <div class="report-main">
            <span>
              <a-tag :color="statusColor(report)">{{ statusLabel(report) }}</a-tag>
              <b>V{{ report.version }} · {{ report.report_title }}</b>
            </span>
            <small>{{ report.report_code }}</small>
            <p>
              {{ report.task_plot_count }} 块图斑 ·
              {{ report.history_snapshot_count }} 个历史快照 ·
              {{ formatTime(report.generated_at) }} ·
              {{ report.generated_by }}（{{ report.generated_by_role }}）
            </p>
            <div class="file-evidence">
              <span><FileExcelOutlined /> XLSX {{ formatBytes(report.xlsx_size_bytes) }}</span>
              <span><FilePdfOutlined /> PDF {{ formatBytes(report.pdf_size_bytes) }}</span>
              <span>ZIP {{ formatBytes(report.bundle_size_bytes) }}</span>
            </div>
            <code :title="report.bundle_checksum_sha256">
              SHA-256 {{ report.bundle_checksum_sha256 }}
            </code>
            <a-alert
              v-if="report.stale_reason"
              class="stale-alert"
              :type="report.status === 'invalid' ? 'error' : 'warning'"
              show-icon
              :message="report.stale_reason"
            />
          </div>
          <a-tooltip
            :title="canDownload ? '下载含 XLSX、PDF 和清单的 ZIP' : '仅项目负责人和甲方可下载'"
          >
            <a-button
              :disabled="!canDownload || !report.download_url"
              :loading="downloadingCode === report.report_code"
              @click="emit('download', report)"
            >
              <CloudDownloadOutlined />下载
            </a-button>
          </a-tooltip>
        </article>
      </div>
      <a-empty v-else description="尚未生成正式面积统计报告" />
    </section>
  </a-modal>
</template>

<style scoped>
.generate-section,
.history-section {
  padding: 14px;
  margin-top: 14px;
  border: 1px solid #dfe6e2;
  border-radius: 7px;
  background: #fbfcfb;
}
.generate-section > header,
.history-section > header,
.generate-actions,
.report-list article,
.report-main > span,
.file-evidence {
  display: flex;
  align-items: center;
}
.generate-section > header,
.history-section > header,
.generate-actions,
.report-list article {
  justify-content: space-between;
}
.generate-section > header,
.history-section > header { margin-bottom: 10px; }
.generate-section header div,
.history-section header div { display: flex; flex-direction: column; }
.generate-section header small,
.history-section header small,
.report-main small,
.report-main p { color: #78867e; }
.generate-section :deep(.ant-input),
.generate-section :deep(.ant-input-textarea) { margin-top: 8px; }
.generate-actions { gap: 14px; margin-top: 10px; }
.generate-actions span { font-size: 12px; color: #718078; }
.report-list { display: grid; gap: 9px; }
.report-list article {
  gap: 16px;
  padding: 12px;
  border: 1px solid #e1e8e4;
  border-radius: 6px;
  background: #fff;
}
.report-main { min-width: 0; flex: 1; }
.report-main > span { gap: 6px; }
.report-main b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.report-main small,
.report-main p,
.report-main code { display: block; margin-top: 5px; font-size: 11px; }
.report-main p { margin-bottom: 0; }
.file-evidence { flex-wrap: wrap; gap: 14px; margin-top: 7px; font-size: 11px; color: #3e6f55; }
.report-main code { overflow: hidden; color: #66756d; text-overflow: ellipsis; white-space: nowrap; }
.stale-alert { margin-top: 8px; }
</style>
