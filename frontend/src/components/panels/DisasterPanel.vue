<script setup lang="ts">
import { DownloadOutlined, FileExcelOutlined, UploadOutlined } from '@ant-design/icons-vue'
import { Empty, message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { onMounted, reactive, ref, watch } from 'vue'

import DisasterImportModal from '@/components/disaster/DisasterImportModal.vue'
import DisasterReportModal from '@/components/disaster/DisasterReportModal.vue'
import { useDisasterStore } from '@/store/disasterStore'
import type {
  DisasterGeoJsonImportPayload,
  DisasterPatchUpdatePayload,
} from '@/types/workbench'

const disasterStore = useDisasterStore()
const {
  canImportComputed,
  canDownloadReportComputed,
  canGenerateReportComputed,
  canReviewComputed,
  currentReportComputed,
  downloadingReportCodeRef,
  generatingReportRef,
  importingRef,
  loadingRef,
  selectedCodeRef,
  selectedPatchComputed,
  reportsRef,
  summaryRef,
} = storeToRefs(disasterStore)
const importModalOpenRef = ref<boolean>(false)
const reportModalOpenRef = ref<boolean>(false)
const form = reactive<{
  severity: DisasterPatchUpdatePayload['severity']
  status: DisasterPatchUpdatePayload['status']
  comment: string
}>({ severity: '轻度', status: 'pending', comment: '' })

watch(selectedPatchComputed, (patch) => {
  if (!patch) return
  form.severity = patch.severity
  form.status = patch.status
}, { immediate: true })

/**
 * 保存当前灾害斑块复核结果。
 * Args:
 *   无。
 * Returns:
 *   Promise<void>: 复核结果保存完成后结束。
 */
const handleSave = async (): Promise<void> => {
  try {
    await disasterStore.updateSelected(form.severity, form.status, form.comment)
    message.success('灾害斑块复核结果已保存')
  } catch {
    // 请求拦截器或权限提示已向用户说明原因。
  }
}

/**
 * 执行灾害模型 GeoJSON 导入并展示批次结果。
 * Args:
 *   payload: 已在弹窗中读取的来源信息和 FeatureCollection。
 * Returns:
 *   Promise<void>: 导入完成后关闭弹窗。
 */
const handleImport = async (
  payload: Omit<DisasterGeoJsonImportPayload, 'operator_code'>,
): Promise<void> => {
  try {
    const result = await disasterStore.importGeoJson(payload)
    importModalOpenRef.value = false
    message.success(
      `批次 ${result.batch_code} 已导入 ${result.imported_count} 个斑块`,
    )
  } catch {
    // 请求拦截器或权限提示已向用户说明原因，保留弹窗便于修正。
  }
}

/**
 * 生成已复核灾害专题报告。
 * Args:
 *   reportTitle: 报告标题。
 *   comment: 生成依据。
 * Returns:
 *   Promise<void>: 报告实体生成并刷新后结束。
 */
const handleGenerateReport = async (
  reportTitle: string,
  comment: string,
): Promise<void> => {
  try {
    const report = await disasterStore.generateReport(reportTitle, comment)
    reportModalOpenRef.value = false
    message.success(`灾害专题报告 ${report.report_code} 已生成并完成校验`)
  } catch {
    // 请求拦截器已显示安全错误，保留弹窗便于修正。
  }
}

/**
 * 下载并保存灾害专题报告 XLSX 实体。
 * Args:
 *   report: 待下载报告摘要。
 * Returns:
 *   Promise<void>: 浏览器下载触发后结束。
 */
const handleDownloadReport = async (
  report: NonNullable<typeof currentReportComputed.value>,
): Promise<void> => {
  try {
    const { blob, filename } = await disasterStore.downloadReport(report)
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    window.URL.revokeObjectURL(url)
  } catch {
    // 请求拦截器已显示安全错误。
  }
}

onMounted(() => { void disasterStore.load() })
</script>

<template>
  <section class="panel">
    <header>
      <span><small>灾害遥感识别</small><strong>受灾斑块</strong></span>
      <div class="header-actions">
        <a-button
          v-if="canImportComputed"
          size="small"
          type="primary"
          @click="importModalOpenRef = true"
        >
          <UploadOutlined />导入
        </a-button>
        <a-button
          v-if="canGenerateReportComputed"
          size="small"
          :disabled="!summaryRef?.items.length || Boolean(summaryRef?.pending_count)"
          @click="reportModalOpenRef = true"
        >
          <FileExcelOutlined />生成报告
        </a-button>
        <a-button size="small" :loading="loadingRef" @click="disasterStore.load">刷新</a-button>
      </div>
    </header>
    <a-alert
      v-if="!canReviewComputed"
      class="permission-alert"
      type="info"
      show-icon
      message="当前身份仅可查看灾害结果"
      description="灾害等级和确认状态只能由质检员或项目负责人复核。"
    />
    <div class="metrics"><div><strong>{{ summaryRef?.total_patches ?? 0 }}</strong><small>斑块</small></div><div><strong>{{ summaryRef?.affected_area_ha ?? 0 }}</strong><small>公顷</small></div><div><strong>{{ summaryRef?.pending_count ?? 0 }}</strong><small>待复核</small></div></div>
    <a-alert
      v-if="summaryRef?.items.length && summaryRef.pending_count > 0"
      class="report-gate"
      type="warning"
      show-icon
      :message="`仍有 ${summaryRef.pending_count} 个斑块待复核，专题报告生成受阻`"
    />
    <div v-if="reportsRef?.items.length" class="report-card">
      <div>
        <small>灾害专题报告</small>
        <strong>{{ currentReportComputed?.report_title || '当前报告待重新生成' }}</strong>
        <em v-if="currentReportComputed">
          {{ currentReportComputed.source_patch_count }} 个斑块 ·
          {{ currentReportComputed.affected_area_ha.toFixed(2) }} 公顷 ·
          {{ (currentReportComputed.file_size_bytes / 1024).toFixed(1) }} KB
        </em>
        <em v-else>历史报告已因灾害数据变化失效</em>
      </div>
      <a-button
        v-if="currentReportComputed"
        size="small"
        :loading="downloadingReportCodeRef === currentReportComputed.report_code"
        :disabled="!canDownloadReportComputed"
        @click="handleDownloadReport(currentReportComputed)"
      >
        <DownloadOutlined />下载
      </a-button>
    </div>
    <div class="patch-list">
      <button
        v-for="item in summaryRef?.items || []"
        :key="item.patch_code"
        :class="{ active: selectedPatchComputed?.patch_code === item.patch_code }"
        @click="selectedCodeRef = item.patch_code"
      >
        <i :class="item.severity" /><span><strong>{{ item.patch_code }}</strong><small>{{ item.disaster_type }} · {{ item.crop_type }}</small></span><a-tag>{{ item.severity }}</a-tag>
      </button>
      <a-empty
        v-if="!loadingRef && !(summaryRef?.items.length)"
        :image="Empty.PRESENTED_IMAGE_SIMPLE"
        description="尚未导入真实灾害模型结果"
      >
        <a-button
          v-if="canImportComputed"
          size="small"
          type="primary"
          @click="importModalOpenRef = true"
        >
          导入 GeoJSON
        </a-button>
      </a-empty>
    </div>
    <div v-if="selectedPatchComputed" class="form">
      <h3>{{ selectedPatchComputed.patch_code }} 人工复核</h3>
      <label>灾害等级</label><a-select
        v-model:value="form.severity"
        style="width: 100%"
        :disabled="!canReviewComputed"
        :options="['轻度', '中度', '重度', '绝收'].map((value) => ({ value }))"
      />
      <label>复核状态</label><a-radio-group v-model:value="form.status" size="small" :disabled="!canReviewComputed"><a-radio-button value="pending">待复核</a-radio-button><a-radio-button value="confirmed">确认</a-radio-button><a-radio-button value="excluded">排除</a-radio-button></a-radio-group>
      <label>复核说明</label><a-textarea v-model:value="form.comment" :rows="2" :disabled="!canReviewComputed" />
      <a-button
        type="primary"
        block
        :disabled="!canReviewComputed"
        @click="handleSave"
      >
        保存复核结果
      </a-button>
      <dl class="source-audit">
        <div><dt>模型来源</dt><dd>{{ selectedPatchComputed.source }}</dd></div>
        <div><dt>来源版本</dt><dd>{{ selectedPatchComputed.source_version || '--' }}</dd></div>
        <div><dt>来源要素</dt><dd>{{ selectedPatchComputed.source_feature_id || '--' }}</dd></div>
        <div><dt>导入批次</dt><dd>{{ selectedPatchComputed.import_batch_code || '--' }}</dd></div>
        <div><dt>导入人</dt><dd>{{ selectedPatchComputed.imported_by || '--' }}</dd></div>
        <div><dt>椭球面积</dt><dd>{{ selectedPatchComputed.affected_area_ha }} 公顷</dd></div>
      </dl>
    </div>
    <DisasterImportModal
      :open="importModalOpenRef"
      :loading="importingRef"
      @cancel="importModalOpenRef = false"
      @submit="handleImport"
    />
    <DisasterReportModal
      :open="reportModalOpenRef"
      :loading="generatingReportRef"
      :task-code="summaryRef?.task_code || 'RS-2026-045'"
      :patch-count="summaryRef?.items.length || 0"
      :affected-area-ha="summaryRef?.affected_area_ha || 0"
      @cancel="reportModalOpenRef = false"
      @submit="handleGenerateReport"
    />
  </section>
</template>

<style scoped>
.panel { height: 100%; padding: 12px; overflow: auto; }
header { display: flex; align-items: center; justify-content: space-between; }
header > span { display: flex; flex-direction: column; }
small { font-size: 7px; color: #8a9690; }
header strong { font-size: 12px; }
.header-actions { display: flex; gap: 5px; }
.metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 5px; margin: 10px 0; }
.permission-alert { margin-top: 10px; }
.report-gate { margin-bottom: 8px; }
.report-card { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 9px; margin-bottom: 8px; background: #f6f8f6; border: 1px solid #dfe7e1; border-radius: 6px; }
.report-card > div { display: grid; min-width: 0; }
.report-card strong { overflow: hidden; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.report-card em { font-size: 7px; font-style: normal; color: #728078; }
.metrics > div { padding: 8px; text-align: center; background: #f5f6f6; border-radius: 5px; }
.metrics strong, .metrics small { display: block; }
.metrics strong { font-size: 16px; color: #cf6044; }
.patch-list button { display: grid; grid-template-columns: 8px 1fr auto; gap: 7px; align-items: center; width: 100%; min-height: 45px; padding: 7px; text-align: left; background: #fff; border: 0; border-bottom: 1px solid #edf0ee; }
.patch-list button.active { background: #fff5f0; }
.patch-list i { width: 7px; height: 7px; background: #e0a142; border-radius: 50%; }
.patch-list i.重度, .patch-list i.绝收 { background: #d44e42; }
.patch-list span { display: flex; flex-direction: column; }
.patch-list strong { font-size: 8px; }
.form { padding-top: 12px; margin-top: 12px; border-top: 1px solid #e6eae8; }
.form h3 { font-size: 10px; }
.form label { display: block; margin: 8px 0 4px; font-size: 8px; color: #68766f; }
.form > :deep(.ant-btn) { margin-top: 9px; }
.source-audit { padding: 8px; margin: 10px 0 0; font-size: 8px; background: #f7f9f8; border: 1px solid #e7ece9; border-radius: 5px; }
.source-audit div { display: grid; grid-template-columns: 58px 1fr; gap: 6px; padding: 2px 0; }
.source-audit dt { color: #87938c; }
.source-audit dd { min-width: 0; margin: 0; overflow: hidden; color: #43544b; text-overflow: ellipsis; white-space: nowrap; }
</style>
