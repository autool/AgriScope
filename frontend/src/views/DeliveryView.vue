<script setup lang="ts">
import {
  CheckCircleOutlined,
  ExportOutlined,
  FileDoneOutlined,
  FileProtectOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref } from 'vue'

import AcceptanceReportModal from '@/components/delivery/AcceptanceReportModal.vue'
import VectorExportModal from '@/components/delivery/VectorExportModal.vue'
import { useAcceptanceReportStore } from '@/store/acceptanceReportStore'
import { useDeliveryStore } from '@/store/deliveryStore'
import { useUserStore } from '@/store/userStore'
import { useVectorExportStore } from '@/store/vectorExportStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  VectorExportGeneratePayload,
  VectorExportPackage,
} from '@/types/vectorExport'
import type { AcceptanceReport } from '@/types/acceptanceReport'

const workbenchStore = useWorkbenchStore()
const deliveryStore = useDeliveryStore()
const userStore = useUserStore()
const vectorExportStore = useVectorExportStore()
const acceptanceReportStore = useAcceptanceReportStore()
const { deliveriesRef } = storeToRefs(deliveryStore)
const {
  canDownloadComputed: canDownloadVectorComputed,
  canGenerateComputed: canGenerateVectorComputed,
  downloadingCodeRef: vectorDownloadingCodeRef,
  generatingRef: vectorGeneratingRef,
  listRef: vectorExportListRef,
  loadingRef: vectorLoadingRef,
  optionsRef: vectorExportOptionsRef,
} = storeToRefs(vectorExportStore)
const { overviewRef } = storeToRefs(workbenchStore)
const {
  canDownloadComputed: canDownloadAcceptanceComputed,
  canGenerateComputed: canGenerateAcceptanceComputed,
  downloadingCodeRef: acceptanceDownloadingCodeRef,
  generatingRef: acceptanceGeneratingRef,
  listRef: acceptanceReportListRef,
  loadingRef: acceptanceLoadingRef,
} = storeToRefs(acceptanceReportStore)
const selectedPackageCodeRef = ref<string | null>(null)
const generatingRef = ref(false)
const vectorExportOpenRef = ref<boolean>(false)
const acceptanceReportOpenRef = ref<boolean>(false)
const selectedPackageComputed = computed(() => deliveriesRef.value?.packages?.find(
  (item) => item.package_code === selectedPackageCodeRef.value,
) || deliveriesRef.value?.packages?.[0] || null)
const canGenerateComputed = computed<boolean>(() => (
  Boolean(deliveriesRef.value?.can_generate)
  && userStore.hasCapability('generate_delivery')
))
const deliveryBlockerComputed = computed<string>(() => {
  if (!deliveriesRef.value?.can_generate) {
    return deliveriesRef.value?.generate_blocker || '任务尚未满足成果生成条件'
  }
  if (!userStore.hasCapability('generate_delivery')) {
    return '当前身份无成果包生成权限，仅项目负责人可执行'
  }
  return '三级审核已完成，当前项目负责人可生成最终成果包'
})

const summaryNumber = (key: string): number => {
  const value = selectedPackageComputed.value?.quality_summary[key]
  return typeof value === 'number' ? value : Number(value || 0)
}

const formatBytes = (value?: number | null): string => {
  if (!value) return '--'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

const evidenceLabel = (status?: string): string => ({
  included: '实体已纳入',
  referenced: '校验后引用',
  not_provided: '未提供',
  legacy: '历史清单',
}[status || 'legacy'] || '历史清单')

const evidenceColor = (status?: string): string => ({
  included: 'green',
  referenced: 'blue',
  not_provided: 'default',
  legacy: 'default',
}[status || 'legacy'] || 'default')

const getDownloadUrl = (downloadUrl: string | null): string | undefined => {
  const userCode = userStore.currentUserComputed?.user_code
  if (!downloadUrl || !userCode || !userStore.hasCapability('download_delivery')) {
    return undefined
  }
  const separator = downloadUrl.includes('?') ? '&' : '?'
  return `${downloadUrl}${separator}user_code=${encodeURIComponent(userCode)}`
}

/**
 * 生成新版本成果交付包。
 * Args:
 *   无。
 * Returns:
 *   Promise<void>: 成果包生成和列表刷新完成后结束。
 */
const handleGenerate = async () => {
  if (!canGenerateComputed.value) {
    message.warning(deliveryBlockerComputed.value)
    return
  }
  generatingRef.value = true
  try {
    const packageData = await deliveryStore.generate(
      `${overviewRef.value?.task?.task_name}最终监测成果`,
    )
    selectedPackageCodeRef.value = packageData.package_code
    message.success(`成果交付包 v${packageData.version} 已生成`)
  } finally {
    generatingRef.value = false
  }
}

const downloadBlob = (blob: Blob, filename: string): void => {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  window.URL.revokeObjectURL(url)
}

/**
 * 生成真实多格式矢量成果包。
 * Args:
 *   payload: 格式、县区、地类和生成依据。
 * Returns:
 *   Promise<void>: 生成并刷新完成后结束。
 */
const handleGenerateVector = async (
  payload: Omit<VectorExportGeneratePayload, 'operator_code'>,
): Promise<void> => {
  try {
    const result = await vectorExportStore.generate(payload)
    message.success(`矢量成果 V${result.version} 已生成，共 ${result.feature_count} 个图斑`)
  } catch {
    // 请求拦截器已显示安全错误，保留弹窗便于修正。
  }
}

/**
 * 下载并保存通过完整格式复核的矢量成果 ZIP。
 * Args:
 *   item: 导出版本摘要。
 * Returns:
 *   Promise<void>: 下载动作触发后结束。
 */
const handleDownloadVector = async (
  item: VectorExportPackage,
): Promise<void> => {
  try {
    const { blob, filename } = await vectorExportStore.download(item)
    downloadBlob(blob, filename)
    message.success(`矢量成果 V${item.version} 已通过完整性校验并开始下载`)
  } catch {
    // 请求拦截器已显示安全错误。
  }
}

/**
 * 生成绑定当前成果包的正式验收报告。
 * Args:
 *   reportTitle: 验收报告标题。
 *   comment: 生成依据。
 * Returns:
 *   Promise<void>: 报告生成和列表刷新完成后结束。
 */
const handleGenerateAcceptance = async (
  reportTitle: string,
  comment: string,
): Promise<void> => {
  try {
    const report = await acceptanceReportStore.generate({
      report_title: reportTitle,
      comment,
    })
    message.success(`成果验收报告 V${report.version} 已生成`)
  } catch {
    // 请求拦截器已显示安全错误，保留弹窗便于查看业务门禁。
  }
}

/**
 * 下载并保存通过 DOCX/PDF 复核的验收报告 ZIP。
 * Args:
 *   report: 待下载验收报告。
 * Returns:
 *   Promise<void>: 下载动作触发后结束。
 */
const handleDownloadAcceptance = async (
  report: AcceptanceReport,
): Promise<void> => {
  try {
    const { blob, filename } = await acceptanceReportStore.download(report)
    downloadBlob(blob, filename)
    message.success(`成果验收报告 V${report.version} 已校验并开始下载`)
  } catch {
    // 请求拦截器已显示安全错误。
  }
}

onMounted(() => {
  void Promise.all([
    deliveryStore.load(),
    vectorExportStore.load(),
    acceptanceReportStore.load(),
  ])
})
</script>

<template>
  <div class="delivery-view">
    <header class="delivery-toolbar">
      <span><FileDoneOutlined /> 成果包生成、校验与归档</span>
      <div>
        <a-button @click="vectorExportOpenRef = true">
          <ExportOutlined />矢量成果
        </a-button>
        <a-button @click="acceptanceReportOpenRef = true">
          <FileProtectOutlined />验收报告
        </a-button>
        <a-button
          type="primary"
          :disabled="!canGenerateComputed"
          :loading="generatingRef"
          @click="handleGenerate"
        >
          生成新版本
        </a-button>
      </div>
    </header>
    <a-alert
      :type="canGenerateComputed ? 'success' : 'warning'"
      show-icon
      :message="deliveryBlockerComputed"
    />

    <div class="delivery-grid">
      <aside class="version-panel">
        <header><span><small>DELIVERY HISTORY</small><strong>交付版本</strong></span><em>{{ deliveriesRef?.packages?.length ?? 0 }} 个</em></header>
        <button
          v-for="item in deliveriesRef?.packages || []"
          :key="item.package_code"
          :class="{ active: selectedPackageComputed?.package_code === item.package_code }"
          @click="selectedPackageCodeRef = item.package_code"
        >
          <i>v{{ item.version }}</i><span><strong>{{ item.package_name }}</strong><small>{{ item.generated_by }} · {{ item.completed_at ? new Date(item.completed_at).toLocaleString('zh-CN') : '--' }}</small></span><a-tag :color="item.is_current ? 'green' : 'default'">{{ item.is_current ? '当前成果' : '历史失效' }}</a-tag>
        </button>
      </aside>

      <main v-if="selectedPackageComputed" class="package-panel">
        <a-alert
          v-if="!selectedPackageComputed.is_current"
          type="warning"
          show-icon
          :message="selectedPackageComputed.stale_reason || '该成果包已失效'"
          description="历史文件仍保留用于审计，但不能作为当前任务成果下载。"
        />
        <section class="package-hero" :class="{ stale: !selectedPackageComputed.is_current }">
          <div><small>FINAL DELIVERY PACKAGE</small><h2>{{ selectedPackageComputed.package_name }}</h2><p>{{ selectedPackageComputed.package_code }}</p></div>
          <div class="acceptance-seal"><CheckCircleOutlined /><strong>{{ selectedPackageComputed.is_current ? '验收就绪' : '历史归档' }}</strong><small>{{ selectedPackageComputed.is_current ? 'SHA-256 已校验' : '禁止作为当前成果下载' }}</small></div>
        </section>
        <section class="package-metrics">
          <div><small>交付版本</small><strong>v{{ selectedPackageComputed.version }}</strong></div>
          <div><small>成果文件</small><strong>{{ selectedPackageComputed.manifest.length }}</strong></div>
          <div><small>质量得分</small><strong>{{ selectedPackageComputed.quality_summary.quality_score }}</strong></div>
          <div><small>实体专题图</small><strong>{{ summaryNumber('thematic_map_count') }}</strong></div>
          <div><small>监理报告</small><strong>{{ summaryNumber('supervision_report_count') }}</strong></div>
          <div><small>文件大小</small><strong>{{ formatBytes(selectedPackageComputed.file_size_bytes) }}</strong></div>
        </section>
        <section class="archive-summary">
          <span><small>多源数据目录</small><strong>{{ summaryNumber('dataset_asset_count') }} 项</strong></span>
          <span><small>影像处理实体</small><strong>{{ summaryNumber('imagery_step_count') }} 项</strong></span>
          <span><small>外业证据</small><strong>{{ selectedPackageComputed.quality_summary.field_evidence_status === 'provided' ? '已提供' : '未提供' }}</strong></span>
          <span><small>灾害证据</small><strong>{{ selectedPackageComputed.quality_summary.disaster_evidence_status === 'provided' ? '已提供' : '未提供' }}</strong></span>
        </section>
        <section class="manifest-section">
          <header>
            <span><small>MANIFEST</small><strong>成果文件清单</strong></span>
            <a-button
              type="primary"
              :href="getDownloadUrl(selectedPackageComputed.download_url)"
              :disabled="!getDownloadUrl(selectedPackageComputed.download_url)"
              target="_blank"
            >
              下载 ZIP
            </a-button>
          </header>
          <div class="manifest-grid">
            <article v-for="item in selectedPackageComputed.manifest" :key="item.path">
              <i><FileDoneOutlined /></i>
              <span>
                <strong>{{ item.category }} · {{ item.format }}</strong>
                <small>{{ item.path }}</small>
                <em>{{ item.description }}</em>
                <code v-if="item.checksum_sha256">SHA {{ item.checksum_sha256.slice(0, 16) }}… · {{ formatBytes(item.file_size_bytes) }}</code>
                <code v-else-if="item.source_entity_code">来源 {{ item.source_entity_code }}</code>
              </span>
              <div class="manifest-state">
                <a-tag :color="evidenceColor(item.evidence_status)">{{ evidenceLabel(item.evidence_status) }}</a-tag>
                <small>{{ item.record_count === null ? '成果文件' : `${item.record_count} 条` }}</small>
              </div>
            </article>
          </div>
        </section>
        <section class="checksum"><span><small>SHA-256 CHECKSUM</small><code>{{ selectedPackageComputed.checksum_sha256 }}</code></span><a-tag :color="selectedPackageComputed.is_current ? 'green' : 'default'">{{ selectedPackageComputed.is_current ? '校验通过' : '历史校验值' }}</a-tag></section>
      </main>
    </div>
    <VectorExportModal
      :open="vectorExportOpenRef"
      :task-code="overviewRef?.task.task_code || '--'"
      :options="vectorExportOptionsRef"
      :items="vectorExportListRef?.items || []"
      :generating="vectorGeneratingRef"
      :loading="vectorLoadingRef"
      :downloading-code="vectorDownloadingCodeRef"
      :can-generate="canGenerateVectorComputed"
      :can-download="canDownloadVectorComputed"
      @cancel="vectorExportOpenRef = false"
      @refresh="vectorExportStore.load"
      @generate="handleGenerateVector"
      @download="handleDownloadVector"
    />
    <AcceptanceReportModal
      :open="acceptanceReportOpenRef"
      :task-code="overviewRef?.task.task_code || '--'"
      :list="acceptanceReportListRef"
      :loading="acceptanceLoadingRef"
      :generating="acceptanceGeneratingRef"
      :downloading-code="acceptanceDownloadingCodeRef"
      :can-generate="canGenerateAcceptanceComputed"
      :can-download="canDownloadAcceptanceComputed"
      @cancel="acceptanceReportOpenRef = false"
      @refresh="acceptanceReportStore.load"
      @generate="handleGenerateAcceptance"
      @download="handleDownloadAcceptance"
    />
  </div>
</template>

<style scoped>
.delivery-view { height: 100%; padding: 10px; overflow: auto; background: #eef3f0; }
.delivery-toolbar { display: flex; align-items: center; justify-content: space-between; height: 44px; padding: 0 12px; margin-bottom: 9px; background: #fff; border: 1px solid #dfe6e2; border-radius: 6px; }
.delivery-toolbar > span { display: flex; gap: 7px; align-items: center; font-size: 11px; font-weight: 600; }
.delivery-toolbar > div { display: flex; gap: 7px; }
.delivery-grid { display: grid; grid-template-columns: 270px minmax(0, 1fr); gap: 10px; margin-top: 9px; }
.version-panel, .package-panel { background: #fff; border: 1px solid #dfe6e2; border-radius: 7px; }
.version-panel { padding: 12px; }
.version-panel > header, .manifest-section > header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.version-panel header > span, .manifest-section header > span { display: flex; flex-direction: column; }
.version-panel small, .manifest-section header small { font-size: 7px; color: #91a099; }
.version-panel strong, .manifest-section header strong { font-size: 10px; }
.version-panel em { font-size: 8px; font-style: normal; color: #7f8c85; }
.version-panel > button { display: grid; grid-template-columns: 30px 1fr auto; gap: 7px; align-items: center; width: 100%; min-height: 55px; padding: 7px; text-align: left; cursor: pointer; background: #fff; border: 0; border-bottom: 1px solid #edf0ee; }
.version-panel > button.active { background: #f0f7f3; box-shadow: inset 3px 0 #4a9b70; }
.version-panel > button > i { display: grid; width: 28px; height: 28px; font-size: 8px; font-style: normal; color: #347957; background: #e7f2eb; border-radius: 50%; place-items: center; }
.version-panel > button > span { display: flex; min-width: 0; flex-direction: column; }
.version-panel > button strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.version-panel > button small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.package-panel { padding: 13px; }
.package-hero { display: flex; align-items: center; justify-content: space-between; padding: 18px; color: #fff; background: linear-gradient(135deg, #214e3a, #3c8b62); border-radius: 7px; }
.package-hero.stale { margin-top: 9px; background: linear-gradient(135deg, #626b66, #858d89); }
.package-hero small { font-size: 7px; color: rgb(255 255 255 / 58%); }
.package-hero h2 { margin: 5px 0; font-size: 18px; color: #fff; }
.package-hero p { margin: 0; font-size: 8px; color: rgb(255 255 255 / 65%); }
.acceptance-seal { display: flex; flex-direction: column; align-items: center; padding: 9px 18px; border: 1px solid rgb(255 255 255 / 25%); border-radius: 7px; }
.acceptance-seal > :first-child { font-size: 24px; }
.acceptance-seal strong { margin-top: 3px; font-size: 10px; }
.acceptance-seal small { font-size: 7px; }
.package-metrics { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; margin: 9px 0; }
.package-metrics > div { padding: 11px; background: #f4f7f5; border-radius: 5px; }
.package-metrics small, .package-metrics strong { display: block; }
.package-metrics small { font-size: 7px; color: #839088; }
.package-metrics strong { margin-top: 3px; font-size: 16px; color: #347957; }
.archive-summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; padding: 10px; margin-bottom: 9px; background: #f8faf9; border: 1px solid #e3e8e5; border-radius: 6px; }
.archive-summary span { display: flex; flex-direction: column; gap: 2px; }
.archive-summary small { font-size: 7px; color: #89958f; }
.archive-summary strong { font-size: 10px; color: #405148; }
.manifest-section { padding: 12px; border: 1px solid #e3e8e5; border-radius: 6px; }
.manifest-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 7px; }
.manifest-grid article { display: grid; grid-template-columns: 29px minmax(0, 1fr) auto; gap: 7px; align-items: center; padding: 9px; background: #f8faf9; border: 1px solid #e8ecea; border-radius: 5px; }
.manifest-grid article > i { display: grid; width: 27px; height: 27px; color: #3d8b63; background: #e7f2eb; border-radius: 4px; place-items: center; }
.manifest-grid article > span { display: flex; min-width: 0; flex-direction: column; }
.manifest-grid strong { font-size: 8px; }
.manifest-grid small, .manifest-grid em { overflow: hidden; font-size: 7px; color: #8b9690; text-overflow: ellipsis; white-space: nowrap; }
.manifest-grid em { font-style: normal; }
.manifest-grid code { overflow: hidden; font-size: 7px; color: #53665c; text-overflow: ellipsis; white-space: nowrap; }
.manifest-state { display: flex; flex-direction: column; gap: 3px; align-items: flex-end; }
.manifest-state small { font-size: 7px; color: #8b9690; }
.checksum { display: flex; align-items: center; justify-content: space-between; padding: 10px; margin-top: 9px; background: #f4f7f5; border-radius: 5px; }
.checksum > span { display: flex; min-width: 0; flex-direction: column; }
.checksum small { font-size: 7px; color: #8b9690; }
.checksum code { overflow: hidden; font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 1280px) {
  .package-metrics { grid-template-columns: repeat(3, 1fr); }
  .manifest-grid { grid-template-columns: 1fr; }
}
</style>
