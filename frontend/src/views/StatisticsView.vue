<script setup lang="ts">
import {
  BarChartOutlined,
  DownloadOutlined,
  FileDoneOutlined,
  UploadOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref } from 'vue'

import StatisticsRankingTable from '@/components/statistics/StatisticsRankingTable.vue'
import StatisticsHistoryImportModal from '@/components/statistics/StatisticsHistoryImportModal.vue'
import StatisticsReportModal from '@/components/statistics/StatisticsReportModal.vue'
import { useStatisticsStore } from '@/store/statisticsStore'
import type {
  AreaGroupItem,
  AreaStatisticsHistoryImportMetadata,
  StatisticsReport,
} from '@/types/workbench'

const statisticsStore = useStatisticsStore()
const {
  canExportComputed,
  canImportHistoryComputed,
  canDownloadReportComputed,
  canGenerateReportComputed,
  downloadingReportCodeRef,
  exportingRef,
  generatingReportRef,
  importingHistoryRef,
  loadingRef,
  reportsRef,
  statisticsRef,
} = storeToRefs(statisticsStore)
const historyImportOpenRef = ref<boolean>(false)
const reportModalOpenRef = ref<boolean>(false)
const rankingDimensionRef = ref<'city' | 'district' | 'village' | 'planting'>(
  'city',
)
const maxTrendAreaComputed = computed<number>(() => Math.max(
  ...(statisticsRef.value?.annual_trend || []).map((item) => item.area_ha),
  1,
))
const trendPeriodComputed = computed<string>(() => {
  const years = statisticsRef.value?.annual_trend.map((item) => item.year) || []
  if (years.length === 0) return '暂无历史快照'
  if (years.length === 1) return `${years[0]} 当前任务实时值`
  return `${years[0]}—${years.at(-1)}`
})
const rankingItemsComputed = computed<AreaGroupItem[]>(() => ({
  city: statisticsRef.value?.by_city || [],
  district: statisticsRef.value?.by_district || [],
  village: statisticsRef.value?.by_village || [],
  planting: statisticsRef.value?.by_planting_mode || [],
})[rankingDimensionRef.value])
const rankingTitleComputed = computed<string>(() => ({
  city: '地级区域',
  district: '县区',
  village: '权属村',
  planting: '种植模式',
})[rankingDimensionRef.value])

const formatYearOverYear = (value: number | null): string => {
  if (value === null) return '基期'
  return `同比 ${value > 0 ? '+' : ''}${value}%`
}

/**
 * 通过 Store 获取授权 CSV 并触发浏览器保存。
 * Args:
 *   无。
 * Returns:
 *   Promise<void>: 下载触发后结束。
 */
const handleExport = async (): Promise<void> => {
  try {
    const { blob, filename } = await statisticsStore.exportCsv()
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
    message.success('任务面积统计 CSV 已生成')
  } catch {
    // 请求拦截器或权限提示已向用户说明原因。
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
 * 下载历史年度统计标准模板。
 * Returns:
 *   Promise<void>: 下载动作触发后结束。
 */
const handleDownloadHistoryTemplate = async (): Promise<void> => {
  try {
    const { blob, filename } = await statisticsStore.downloadHistoryTemplate()
    downloadBlob(blob, filename)
  } catch {
    // 请求拦截器已显示安全错误。
  }
}

/**
 * 导入真实历史年度统计并刷新趋势。
 * Args:
 *   file: 原始 CSV 文件。
 *   metadata: 来源、冲突策略和导入依据。
 * Returns:
 *   Promise<void>: 导入完成后结束。
 */
const handleImportHistory = async (
  file: File,
  metadata: Omit<AreaStatisticsHistoryImportMetadata, 'operator_code'>,
): Promise<void> => {
  try {
    const result = await statisticsStore.importHistoryCsv(file, metadata)
    historyImportOpenRef.value = false
    message.success(
      `批次 ${result.batch_code} 已导入 ${result.imported_count} 个年度，替换 ${result.replaced_count} 个年度`,
    )
  } catch {
    // 请求拦截器已显示安全错误，保留弹窗便于修正。
  }
}

/**
 * 生成服务端正式面积统计报告包。
 * Args:
 *   reportTitle: 报告标题。
 *   comment: 生成依据。
 * Returns:
 *   Promise<void>: 生成完成后结束。
 */
const handleGenerateReport = async (
  reportTitle: string,
  comment: string,
): Promise<void> => {
  try {
    const report = await statisticsStore.generateReport(reportTitle, comment)
    message.success(`正式统计报告 ${report.report_code} 已生成`)
  } catch {
    // 请求拦截器已显示安全错误，保留弹窗便于修正。
  }
}

/**
 * 下载服务端校验后的正式统计报告 ZIP。
 * Args:
 *   report: 报告摘要。
 * Returns:
 *   Promise<void>: 下载动作触发后结束。
 */
const handleDownloadReport = async (
  report: StatisticsReport,
): Promise<void> => {
  try {
    const { blob, filename } = await statisticsStore.downloadReport(report)
    downloadBlob(blob, filename)
    message.success(`报告 V${report.version} 已通过完整性校验并开始下载`)
  } catch {
    // 请求拦截器已显示安全错误。
  }
}

onMounted(() => {
  void statisticsStore.load()
})
</script>

<template>
  <div class="statistics-view">
    <header class="statistics-toolbar">
      <span>
        <BarChartOutlined />
        <b>PostGIS 任务作用域面积统计</b>
        <small>{{ statisticsRef?.task_code || '--' }} · {{ statisticsRef?.monitor_year || '--' }} 年</small>
      </span>
      <div>
        <a-tooltip
          :title="canImportHistoryComputed ? '导入有来源审计的历史年度统计' : '仅项目负责人可导入历史统计'"
        >
          <a-button
            size="small"
            :disabled="!canImportHistoryComputed"
            @click="historyImportOpenRef = true"
          >
            <UploadOutlined />导入历史快照
          </a-button>
        </a-tooltip>
        <a-tooltip title="生成、查看和下载 XLSX/PDF 正式统计报告">
          <a-button size="small" @click="reportModalOpenRef = true">
            <FileDoneOutlined />正式报告
          </a-button>
        </a-tooltip>
        <a-tooltip
          :title="canExportComputed ? '导出任务多维统计 CSV' : '仅项目负责人可导出统计成果'"
        >
          <a-button
            size="small"
            :disabled="!canExportComputed"
            :loading="exportingRef"
            @click="handleExport"
          >
            <DownloadOutlined />导出 CSV
          </a-button>
        </a-tooltip>
        <a-button size="small" :loading="loadingRef" @click="statisticsStore.load">刷新统计</a-button>
      </div>
    </header>

    <a-alert
      class="scope-alert"
      type="info"
      show-icon
      message="统计口径：当前任务明确分配的有效图斑"
      :description="`通过 task_plots 限定 ${statisticsRef?.total_plot_count ?? 0} 块；已删除或未分配给本任务的图斑不参与汇总。`"
    />

    <section class="metric-grid">
      <div><small>任务图斑</small><strong>{{ statisticsRef?.total_plot_count ?? 0 }}</strong><span>块</span></div>
      <div><small>监测总面积</small><strong>{{ statisticsRef?.total_area_ha ?? 0 }}</strong><span>公顷</span></div>
      <div><small>折合面积</small><strong>{{ statisticsRef?.total_area_mu ?? 0 }}</strong><span>亩</span></div>
      <div><small>耕地面积</small><strong>{{ statisticsRef?.farmland_area_ha ?? 0 }}</strong><span>公顷</span></div>
      <div><small>作物录入完成率</small><strong>{{ statisticsRef?.crop_assignment_rate ?? 0 }}%</strong><span>{{ statisticsRef?.crop_assigned_plot_count ?? 0 }} 块已录入</span></div>
    </section>

    <div class="analysis-grid">
      <section>
        <header><span><small>CROP STRUCTURE</small><strong>作物种植面积结构</strong></span><em>公顷 / 占比</em></header>
        <div class="horizontal-chart">
          <div v-for="(item, index) in statisticsRef?.by_crop_type || []" :key="item.label">
            <span>{{ item.label }}</span>
            <div><i :class="`tone-${index}`" :style="{ width: `${item.percentage}%` }" /></div>
            <strong>{{ item.area_ha }}</strong><em>{{ item.percentage }}%</em>
          </div>
        </div>
        <a-empty v-if="!(statisticsRef?.by_crop_type.length)" description="暂无作物统计" />
      </section>

      <section>
        <header><span><small>ANNUAL TREND</small><strong>年度面积变化趋势</strong></span><em>{{ trendPeriodComputed }}</em></header>
        <div
          v-if="statisticsRef?.annual_trend.length"
          class="trend-chart"
          :style="{ gridTemplateColumns: `repeat(${statisticsRef.annual_trend.length}, minmax(70px, 1fr))` }"
        >
          <div v-for="item in statisticsRef.annual_trend" :key="item.year">
            <span>{{ item.area_ha }} ha</span>
            <div><i :style="{ height: `${Math.max(item.area_ha / maxTrendAreaComputed * 100, 8)}%` }" /></div>
            <strong>{{ item.year }}</strong>
            <small>{{ formatYearOverYear(item.year_over_year) }}</small>
            <em
              class="trend-source"
              :title="`${item.source_name}${item.source_version ? ` · ${item.source_version}` : ''}`"
            >
              {{ item.is_current ? '任务实时值' : item.source_name }}
            </em>
          </div>
        </div>
        <a-empty v-else description="暂无真实年度统计快照" />
      </section>

      <section class="ranking-section">
        <header>
          <span><small>ADMINISTRATIVE RANKING</small><strong>多维面积排名</strong></span>
          <a-radio-group v-model:value="rankingDimensionRef" size="small">
            <a-radio-button value="city">地级区域</a-radio-button>
            <a-radio-button value="district">县区</a-radio-button>
            <a-radio-button value="village">权属村</a-radio-button>
            <a-radio-button value="planting">种植模式</a-radio-button>
          </a-radio-group>
        </header>
        <StatisticsRankingTable
          :items="rankingItemsComputed"
          :title="rankingTitleComputed"
        />
      </section>
    </div>
    <StatisticsHistoryImportModal
      :open="historyImportOpenRef"
      :loading="importingHistoryRef"
      :monitor-year="statisticsRef?.monitor_year || null"
      @cancel="historyImportOpenRef = false"
      @submit="handleImportHistory"
      @download-template="handleDownloadHistoryTemplate"
    />
    <StatisticsReportModal
      :open="reportModalOpenRef"
      :task-code="statisticsRef?.task_code || '--'"
      :monitor-year="statisticsRef?.monitor_year || null"
      :reports="reportsRef?.items || []"
      :generating="generatingReportRef"
      :downloading-code="downloadingReportCodeRef"
      :can-generate="canGenerateReportComputed"
      :can-download="canDownloadReportComputed"
      @cancel="reportModalOpenRef = false"
      @generate="handleGenerateReport"
      @download="handleDownloadReport"
      @refresh="statisticsStore.load"
    />
  </div>
</template>

<style scoped>
.statistics-view { height: 100%; padding: 10px; overflow: auto; background: #f1f4f2; }
.statistics-toolbar { display: flex; align-items: center; justify-content: space-between; min-height: 46px; padding: 0 12px; margin-bottom: 9px; background: #fff; border: 1px solid #dfe6e2; border-radius: 6px; }
.statistics-toolbar > span { display: flex; gap: 7px; align-items: center; font-size: 11px; }
.statistics-toolbar > span small { font-size: 8px; font-weight: 400; color: #819087; }
.statistics-toolbar > div { display: flex; gap: 6px; }
.scope-alert { margin-bottom: 9px; }
.metric-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 9px; }
.metric-grid > div { padding: 14px; background: #fff; border: 1px solid #dfe6e2; border-radius: 7px; }
.metric-grid small, .metric-grid strong, .metric-grid span { display: block; }
.metric-grid small { font-size: 8px; color: #7f8c85; }
.metric-grid strong { margin-top: 3px; overflow: hidden; font-size: 23px; color: #2f7452; text-overflow: ellipsis; white-space: nowrap; }
.metric-grid span { font-size: 8px; color: #8b9690; }
.analysis-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; margin-top: 9px; }
.analysis-grid > section { min-height: 225px; padding: 15px; background: #fff; border: 1px solid #dfe6e2; border-radius: 7px; }
.analysis-grid section > header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.analysis-grid header > span { display: flex; flex-direction: column; }
.analysis-grid header small { font-size: 7px; color: #91a099; }
.analysis-grid header strong { font-size: 11px; }
.analysis-grid header em { font-size: 8px; font-style: normal; color: #7e8b84; }
.horizontal-chart > div { display: grid; grid-template-columns: 76px 1fr 46px 38px; gap: 7px; align-items: center; min-height: 35px; font-size: 8px; }
.horizontal-chart > div > div { height: 10px; overflow: hidden; background: #edf1ef; border-radius: 5px; }
.horizontal-chart i { display: block; height: 100%; background: #409567; border-radius: 5px; }
.horizontal-chart .tone-1 { background: #e2a03d; }
.horizontal-chart .tone-2 { background: #5786b6; }
.horizontal-chart .tone-3 { background: #9671b2; }
.horizontal-chart .tone-4 { background: #d46853; }
.horizontal-chart strong, .horizontal-chart em { text-align: right; }
.horizontal-chart em { font-style: normal; color: #718078; }
.trend-chart { display: grid; gap: 16px; height: 175px; overflow-x: auto; }
.trend-chart > div { display: grid; grid-template-rows: 18px 1fr 18px 16px 16px; min-width: 70px; text-align: center; }
.trend-chart > div > span { font-size: 8px; }
.trend-chart > div > div { display: flex; align-items: end; justify-content: center; border-bottom: 1px solid #dfe5e2; }
.trend-chart i { width: 44px; min-height: 8%; background: linear-gradient(#78bd98, #347c57); border-radius: 5px 5px 0 0; }
.trend-chart strong { padding-top: 4px; font-size: 9px; }
.trend-chart small { font-size: 7px; color: #3f9164; }
.trend-source { overflow: hidden; font-size: 7px !important; color: #839087 !important; text-overflow: ellipsis; white-space: nowrap; }
.ranking-section { grid-column: 1 / -1; }
@media (max-width: 1100px) {
  .metric-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .analysis-grid { grid-template-columns: 1fr; }
  .ranking-section { grid-column: auto; }
}
</style>
