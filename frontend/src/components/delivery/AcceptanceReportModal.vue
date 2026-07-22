<script setup lang="ts">
import {
  CloudDownloadOutlined,
  FilePdfOutlined,
  FileWordOutlined,
  ReloadOutlined,
} from '@ant-design/icons-vue'
import { computed, ref, watch } from 'vue'

import type {
  AcceptanceReport,
  AcceptanceReportList,
} from '@/types/acceptanceReport'

const props = defineProps<{
  open: boolean
  taskCode: string
  list: AcceptanceReportList | null
  loading: boolean
  generating: boolean
  downloadingCode: string | null
  canGenerate: boolean
  canDownload: boolean
}>()

const emit = defineEmits<{
  cancel: []
  refresh: []
  generate: [reportTitle: string, comment: string]
  download: [report: AcceptanceReport]
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
  if (value >= 1024) return `${(value / 1024).toFixed(2)} KB`
  return `${value} B`
}

const formatTime = (value: string): string => new Date(value).toLocaleString('zh-CN')

const statusLabel = (report: AcceptanceReport): string => {
  if (report.status === 'invalid') return '实体无效'
  return report.is_current ? '当前验收材料' : '历史版本'
}

const statusColor = (report: AcceptanceReport): string => {
  if (report.status === 'invalid') return 'red'
  return report.is_current ? 'green' : 'default'
}

const fileEvidence = (
  report: AcceptanceReport,
  format: 'DOCX' | 'PDF',
) => report.files.find((item) => item.format === format)

watch(
  () => props.open,
  (open) => {
    if (!open) return
    reportTitleRef.value ||= `${props.taskCode} 农业遥感监测成果验收报告`
    commentRef.value ||= '依据当前有效成果交付包、三级审核记录和质量门禁生成正式送审材料。'
  },
  { immediate: true },
)
</script>

<template>
  <a-modal
    :open="open"
    title="成果验收正式报告"
    width="960px"
    :footer="null"
    @cancel="emit('cancel')"
  >
    <a-alert
      type="info"
      show-icon
      message="绑定当前成果交付包的正式验收材料"
      description="DOCX、自动分页 PDF 和 manifest.json 均由服务端生成；报告冻结任务图斑、成果包编号/大小/SHA-256、质量摘要、三级审核和完整成果清单，来源变化后当前版本自动失效。"
    />

    <a-alert
      v-if="list?.generate_blocker"
      class="gate-alert"
      type="warning"
      show-icon
      :message="list.generate_blocker"
    />

    <section class="generate-section">
      <header>
        <span>
          <strong>生成新版本</strong>
          <small>
            {{ taskCode }} · 成果包
            {{ list?.current_delivery_package_code || '尚未就绪' }}
          </small>
        </span>
        <a-tag :color="canGenerate ? 'green' : 'default'">
          {{ canGenerate ? '项目负责人可生成' : '当前不可生成' }}
        </a-tag>
      </header>
      <label>
        <span>报告标题</span>
        <a-input
          v-model:value="reportTitleRef"
          :maxlength="200"
          :disabled="!canGenerate"
        />
      </label>
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
      <div class="generate-actions">
        <span>内容：工作量统计、质量与精度评价、三级审核、成果清单和签署栏</span>
        <a-button
          type="primary"
          :disabled="!canSubmitComputed"
          :loading="generating"
          @click="emit('generate', reportTitleRef.trim(), commentRef.trim())"
        >
          生成 DOCX / PDF 报告包
        </a-button>
      </div>
    </section>

    <section class="history-section">
      <header>
        <span>
          <strong>报告版本历史</strong>
          <small>{{ list?.items.length || 0 }} 个受控版本</small>
        </span>
        <a-button size="small" :loading="loading" @click="emit('refresh')">
          <ReloadOutlined />刷新
        </a-button>
      </header>
      <div v-if="list?.items.length" class="report-list">
        <article v-for="report in list.items" :key="report.report_code">
          <div class="report-main">
            <span>
              <a-tag :color="statusColor(report)">{{ statusLabel(report) }}</a-tag>
              <b>V{{ report.version }} · {{ report.report_title }}</b>
            </span>
            <small>{{ report.report_code }}</small>
            <p>
              {{ report.task_plot_count }} 个图斑 ·
              {{ report.delivery_manifest_count }} 项成果清单 ·
              {{ formatTime(report.generated_at) }} · {{ report.generated_by }}
            </p>
            <div class="file-evidence">
              <span>
                <FileWordOutlined />
                DOCX {{ formatBytes(fileEvidence(report, 'DOCX')?.file_size_bytes || 0) }}
              </span>
              <span>
                <FilePdfOutlined />
                PDF {{ formatBytes(fileEvidence(report, 'PDF')?.file_size_bytes || 0) }} ·
                {{ fileEvidence(report, 'PDF')?.page_count || '--' }} 页
              </span>
              <span>ZIP {{ formatBytes(report.bundle_size_bytes) }}</span>
            </div>
            <code :title="report.bundle_checksum_sha256">
              ZIP SHA-256 {{ report.bundle_checksum_sha256 }}
            </code>
            <small>绑定成果包：{{ report.delivery_package_code }}</small>
            <a-alert
              v-if="report.stale_reason"
              class="stale-alert"
              :type="report.status === 'invalid' ? 'error' : 'warning'"
              show-icon
              :message="report.stale_reason"
            />
          </div>
          <a-tooltip
            :title="canDownload ? '下载并重新校验 DOCX、PDF 和清单' : '仅项目负责人和甲方可下载'"
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
      <a-empty v-else description="尚未生成成果验收正式报告" />
    </section>
  </a-modal>
</template>

<style scoped>
.gate-alert { margin-top: 12px; }
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
.report-list article { justify-content: space-between; }
.generate-section > header,
.history-section > header { margin-bottom: 11px; }
.generate-section header > span,
.history-section header > span,
.report-main { display: flex; flex-direction: column; }
.generate-section header small,
.history-section header small,
.report-main small,
.report-main p { color: #78867e; }
.generate-section label { display: grid; gap: 5px; margin-top: 9px; }
.generate-section label > span { font-size: 12px; color: #58675f; }
.generate-actions { gap: 16px; margin-top: 11px; }
.generate-actions > span { font-size: 12px; color: #718078; }
.report-list { display: grid; gap: 9px; }
.report-list article {
  gap: 16px;
  padding: 12px;
  border: 1px solid #e1e8e4;
  border-radius: 6px;
  background: #fff;
}
.report-main { min-width: 0; gap: 4px; }
.report-main > span { gap: 6px; }
.report-main b,
.report-main code,
.report-main small { overflow-wrap: anywhere; }
.report-main p { margin: 0; }
.file-evidence { flex-wrap: wrap; gap: 12px; font-size: 12px; color: #52625a; }
.report-main code { font-size: 11px; color: #607068; }
.stale-alert { margin-top: 5px; }
@media (max-width: 760px) {
  .generate-actions,
  .report-list article { align-items: stretch; flex-direction: column; }
}
</style>
