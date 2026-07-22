<script setup lang="ts">
import {
  CheckCircleOutlined,
  FileProtectOutlined,
  IssuesCloseOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  ScheduleOutlined,
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import type { TablePaginationConfig } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref, watch } from 'vue'

import SupervisionCountyEvaluationModal from '@/components/supervision/SupervisionCountyEvaluationModal.vue'
import SupervisionFindingDrawer from '@/components/supervision/SupervisionFindingDrawer.vue'
import SupervisionFindingModal from '@/components/supervision/SupervisionFindingModal.vue'
import SupervisionInspectionModal from '@/components/supervision/SupervisionInspectionModal.vue'
import SupervisionPlanModal from '@/components/supervision/SupervisionPlanModal.vue'
import SupervisionPlanWorkspace from '@/components/supervision/SupervisionPlanWorkspace.vue'
import { useSupervisionStore } from '@/store/supervisionStore'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  SupervisionCountyEvaluationPayload,
  SupervisionFinding,
  SupervisionFindingCreatePayload,
  SupervisionInspection,
  SupervisionInspectionCreatePayload,
  SupervisionPlan,
  SupervisionPlanCreatePayload,
  SupervisionRectificationPayload,
  SupervisionReinspectionPayload,
} from '@/types/supervision'

const supervisionStore = useSupervisionStore()
const userStore = useUserStore()
const workbenchStore = useWorkbenchStore()
const {
  overviewRef,
  samplePageRef,
  loadingRef,
  samplesLoadingRef,
  savingRef,
} = storeToRefs(supervisionStore)

const selectedPlanCodeRef = ref<string>('')
const selectedInspectionRef = ref<SupervisionInspection | null>(null)
const selectedFindingRef = ref<SupervisionFinding | null>(null)
const samplesOpenRef = ref<boolean>(false)
const sampleRegionCodeRef = ref<string | null>(null)
const planModalRef = ref<InstanceType<typeof SupervisionPlanModal> | null>(null)
const inspectionModalRef = ref<InstanceType<typeof SupervisionInspectionModal> | null>(null)
const findingModalRef = ref<InstanceType<typeof SupervisionFindingModal> | null>(null)
const evaluationModalRef = ref<InstanceType<typeof SupervisionCountyEvaluationModal> | null>(null)

const currentUserCodeComputed = computed<string | null>(() => (
  userStore.currentUserComputed?.user_code || null
))
const canSuperviseComputed = computed<boolean>(() => userStore.hasCapability('supervise_project'))
const canRectifyComputed = computed<boolean>(() => userStore.hasCapability('rectify_supervision_finding'))
const canDownloadComputed = computed<boolean>(() => userStore.hasCapability('download_supervision_report'))
const selectedPlanComputed = computed<SupervisionPlan | null>(() => (
  overviewRef.value?.plans.find((plan) => plan.plan_code === selectedPlanCodeRef.value)
  || overviewRef.value?.plans[0]
  || null
))

watch(() => overviewRef.value?.plans, (plans) => {
  if (!plans?.length) {
    selectedPlanCodeRef.value = ''
    return
  }
  if (!plans.some((plan) => plan.plan_code === selectedPlanCodeRef.value)) {
    selectedPlanCodeRef.value = plans[0].plan_code
  }
})

const createPlan = async (payload: SupervisionPlanCreatePayload): Promise<void> => {
  try {
    await supervisionStore.createPlan(payload)
    planModalRef.value?.close()
    message.success('独立监理计划已创建，并固化真实图斑样本和任务数据快照')
  } catch {
    // 请求拦截器已显示安全错误。
  }
}

const createInspection = async (
  payload: SupervisionInspectionCreatePayload,
): Promise<void> => {
  const plan = selectedPlanComputed.value
  if (!plan) return
  try {
    await supervisionStore.createInspection(plan.plan_code, payload)
    inspectionModalRef.value?.close()
    message.success('独立过程检查及证据已登记')
  } catch {
    // 请求拦截器已显示安全错误。
  }
}

const openFindingModal = (inspection: SupervisionInspection): void => {
  selectedInspectionRef.value = inspection
  findingModalRef.value?.open()
}

const createFinding = async (
  payload: SupervisionFindingCreatePayload,
): Promise<void> => {
  const plan = selectedPlanComputed.value
  const inspection = selectedInspectionRef.value
  if (!plan || !inspection) return
  try {
    await supervisionStore.createFinding(plan.plan_code, inspection.inspection_code, payload)
    findingModalRef.value?.close()
    message.success('监理问题、整改期限和证据已登记')
  } catch {
    // 请求拦截器已显示安全错误。
  }
}

const submitRectification = async (
  payload: SupervisionRectificationPayload,
): Promise<void> => {
  const plan = selectedPlanComputed.value
  const finding = selectedFindingRef.value
  if (!plan || !finding) return
  try {
    await supervisionStore.submitRectification(plan.plan_code, finding.finding_code, payload)
    selectedFindingRef.value = null
    message.success('整改证据已提交，等待独立监理复检')
  } catch {
    // 请求拦截器已显示安全错误。
  }
}

const reinspectFinding = async (
  payload: SupervisionReinspectionPayload,
): Promise<void> => {
  const plan = selectedPlanComputed.value
  const finding = selectedFindingRef.value
  if (!plan || !finding) return
  try {
    await supervisionStore.reinspectFinding(plan.plan_code, finding.finding_code, payload)
    selectedFindingRef.value = null
    message.success(payload.result === 'passed' ? '复检通过，问题已闭环' : '复检未通过，问题已退回继续整改')
  } catch {
    // 请求拦截器已显示安全错误。
  }
}

const evaluateCounty = async (
  regionCode: string,
  payload: SupervisionCountyEvaluationPayload,
): Promise<void> => {
  const plan = selectedPlanComputed.value
  if (!plan) return
  try {
    await supervisionStore.evaluateCounty(plan.plan_code, regionCode, payload)
    evaluationModalRef.value?.close()
    message.success('县区监理评价已保存并记录修改前后值')
  } catch {
    // 请求拦截器已显示安全错误。
  }
}

const generateReport = (): void => {
  const plan = selectedPlanComputed.value
  const operatorCode = currentUserCodeComputed.value
  if (!plan || !operatorCode) return
  Modal.confirm({
    title: '生成不可变独立监理报告？',
    content: '报告将写入实体 JSON 文件并保存大小、SHA-256 和完整证据清单；生成后计划冻结，不能继续修改。',
    okText: '生成并冻结',
    async onOk() {
      try {
        await supervisionStore.generateReport(plan.plan_code, {
          operator_code: operatorCode,
          comment: '完成当前抽样计划全部监理证据并生成不可变报告',
        })
        message.success('不可变独立监理报告已生成并通过实体校验')
      } catch {
        // 请求拦截器已显示安全错误。
      }
    },
  })
}

const openSamples = async (): Promise<void> => {
  const plan = selectedPlanComputed.value
  if (!plan) return
  samplesOpenRef.value = true
  sampleRegionCodeRef.value = null
  await supervisionStore.loadSamples(plan.plan_code)
}

const loadSamplePage = async (page: number, pageSize: number): Promise<void> => {
  const plan = selectedPlanComputed.value
  if (!plan) return
  await supervisionStore.loadSamples(
    plan.plan_code,
    page,
    pageSize,
    sampleRegionCodeRef.value,
  )
}

const handleSampleTableChange = (pagination: TablePaginationConfig): void => {
  void loadSamplePage(pagination.current || 1, pagination.pageSize || 50)
}

const reportDownloadUrl = (plan: SupervisionPlan): string | undefined => {
  const userCode = currentUserCodeComputed.value
  if (!plan.report || !userCode || !canDownloadComputed.value) return undefined
  const params = new URLSearchParams({
    user_code: userCode,
    project_code: workbenchStore.projectCodeComputed,
    task_code: workbenchStore.taskCodeComputed,
  })
  return `${plan.report.download_url}?${params.toString()}`
}

onMounted(() => {
  void supervisionStore.load()
})
</script>

<template>
  <div class="supervision-view">
    <header class="page-heading">
      <span><SafetyCertificateOutlined /><i><small>INDEPENDENT SUPERVISION</small><strong>独立项目监理</strong><em>真实抽样、过程检查、整改复检、县区评价与不可变报告</em></i></span>
      <div>
        <a-tag color="green">{{ overviewRef?.work_areas.filter((item) => item.plot_count > 0).length || 0 }} 个可抽样县区</a-tag>
        <a-button :loading="loadingRef" @click="supervisionStore.load"><ReloadOutlined /> 刷新</a-button>
        <a-button type="primary" :disabled="!canSuperviseComputed || !overviewRef?.work_areas.some((item) => item.plot_count > 0)" @click="planModalRef?.open()"><ScheduleOutlined /> 创建监理计划</a-button>
      </div>
    </header>

    <a-spin :spinning="loadingRef">
      <template v-if="overviewRef">
        <section class="metric-grid">
          <article><ScheduleOutlined /><span><strong>{{ overviewRef.metrics.active_plan_count }} / {{ overviewRef.metrics.plan_count }}</strong><small>活动 / 全部计划</small><em>与质检、三级审核分离</em></span></article>
          <article><CheckCircleOutlined /><span><strong>{{ overviewRef.metrics.sampled_plot_count.toLocaleString() }}</strong><small>显式抽样图斑</small><em>绑定任务版本快照</em></span></article>
          <article><FileProtectOutlined /><span><strong>{{ overviewRef.metrics.inspection_count }}</strong><small>独立过程检查</small><em>证据地址和监理身份可追溯</em></span></article>
          <article :class="{ warning: overviewRef.metrics.open_finding_count > 0 }"><IssuesCloseOutlined /><span><strong>{{ overviewRef.metrics.open_finding_count }}</strong><small>未闭环问题</small><em>{{ overviewRef.metrics.overdue_finding_count }} 项已逾期</em></span></article>
        </section>

        <a-alert
          v-for="blocker in overviewRef.blockers"
          :key="blocker"
          class="blocker-alert"
          type="warning"
          show-icon
          :message="blocker"
        />
        <a-alert
          v-if="!canSuperviseComputed"
          class="blocker-alert"
          type="info"
          show-icon
          message="当前身份不是独立监理"
          description="项目负责人、内业和质检可以查看监理证据或提交整改，但不能代替独立监理创建计划、检查、复检和评价。"
        />

        <section class="workspace-grid">
          <aside class="plan-list">
            <header><strong>监理计划</strong><span>{{ overviewRef.plans.length }}</span></header>
            <a-empty v-if="!overviewRef.plans.length" description="尚未创建监理计划" />
            <button
              v-for="plan in overviewRef.plans"
              :key="plan.plan_code"
              type="button"
              :class="{ active: selectedPlanComputed?.plan_code === plan.plan_code }"
              @click="selectedPlanCodeRef = plan.plan_code"
            >
              <span><strong>{{ plan.plan_name }}</strong><small>{{ plan.plan_code }} · {{ plan.region_codes.length }} 县区</small></span>
              <a-badge :count="plan.open_finding_count" :show-zero="false" />
              <em>{{ plan.sample_count.toLocaleString() }} 样本</em>
            </button>
          </aside>

          <SupervisionPlanWorkspace
            v-if="selectedPlanComputed"
            :plan="selectedPlanComputed"
            :can-supervise="canSuperviseComputed"
            :can-rectify="canRectifyComputed"
            :report-download-url="reportDownloadUrl(selectedPlanComputed)"
            :saving="savingRef"
            @create-inspection="inspectionModalRef?.open()"
            @create-finding="openFindingModal"
            @open-finding="selectedFindingRef = $event"
            @view-samples="openSamples"
            @evaluate-county="evaluationModalRef?.open()"
            @generate-report="generateReport"
          />
          <div v-else class="empty-workspace">
            <a-result
              status="info"
              title="尚未创建独立监理计划"
              sub-title="使用独立监理身份，从当前任务 122 个县区和真实图斑中建立可复现抽样。"
            />
          </div>
        </section>
      </template>
    </a-spin>

    <SupervisionPlanModal
      ref="planModalRef"
      :work-areas="overviewRef?.work_areas || []"
      :operator-code="currentUserCodeComputed"
      :saving="savingRef"
      @create="createPlan"
    />
    <SupervisionInspectionModal
      v-if="selectedPlanComputed"
      ref="inspectionModalRef"
      :plan-code="selectedPlanComputed.plan_code"
      :operator-code="currentUserCodeComputed"
      :saving="savingRef"
      @create="createInspection"
    />
    <SupervisionFindingModal
      v-if="selectedPlanComputed && selectedInspectionRef"
      ref="findingModalRef"
      :plan-code="selectedPlanComputed.plan_code"
      :inspection-code="selectedInspectionRef.inspection_code"
      :region-codes="selectedPlanComputed.region_codes"
      :work-areas="overviewRef?.work_areas || []"
      :operator-code="currentUserCodeComputed"
      :saving="savingRef"
      @create="createFinding"
    />
    <SupervisionCountyEvaluationModal
      v-if="selectedPlanComputed"
      ref="evaluationModalRef"
      :plan-code="selectedPlanComputed.plan_code"
      :region-codes="selectedPlanComputed.region_codes"
      :work-areas="overviewRef?.work_areas || []"
      :evaluations="selectedPlanComputed.county_evaluations"
      :operator-code="currentUserCodeComputed"
      :saving="savingRef"
      @evaluate="evaluateCounty"
    />
    <SupervisionFindingDrawer
      :finding="selectedFindingRef"
      :operator-code="currentUserCodeComputed"
      :can-rectify="canRectifyComputed"
      :can-reinspect="canSuperviseComputed"
      :saving="savingRef"
      @close="selectedFindingRef = null"
      @rectify="submitRectification"
      @reinspect="reinspectFinding"
    />

    <a-drawer v-model:open="samplesOpenRef" width="760" title="监理计划显式样本">
      <template v-if="selectedPlanComputed">
        <a-alert
          type="info"
          show-icon
          :message="`共 ${selectedPlanComputed.sample_count.toLocaleString()} 个真实任务图斑样本`"
          description="样本分页完整读取，不在概览中下载图斑完整几何，也不静默截断。"
        />
        <a-select
          v-model:value="sampleRegionCodeRef"
          allow-clear
          placeholder="全部抽样县区"
          class="sample-filter"
          @change="loadSamplePage(1, samplePageRef?.page_size || 50)"
        >
          <a-select-option v-for="regionCode in selectedPlanComputed.region_codes" :key="regionCode" :value="regionCode">
            {{ overviewRef?.work_areas.find((item) => item.region_code === regionCode)?.region_name || regionCode }} · {{ selectedPlanComputed.region_sample_counts[regionCode] || 0 }} 个
          </a-select-option>
        </a-select>
        <a-table
          :loading="samplesLoadingRef"
          :data-source="samplePageRef?.items || []"
          row-key="plot_code"
          size="small"
          :pagination="{
            current: samplePageRef?.page || 1,
            pageSize: samplePageRef?.page_size || 50,
            total: samplePageRef?.total || 0,
            showSizeChanger: true,
          }"
          @change="handleSampleTableChange"
        >
          <a-table-column title="图斑编号" data-index="plot_code" />
          <a-table-column title="县区" data-index="region_name" />
          <a-table-column title="版本快照" data-index="plot_version_snapshot" width="110" />
          <a-table-column title="县区抽样序号" data-index="selection_rank" width="120" />
        </a-table>
      </template>
    </a-drawer>
  </div>
</template>

<style scoped>
.supervision-view { height: 100%; padding: 12px; overflow: auto; background: #f1f4f2; }
.page-heading, .page-heading > span, .page-heading > div, .metric-grid article { display: flex; align-items: center; }
.page-heading { justify-content: space-between; padding: 13px 15px; background: #fff; border: 1px solid #dfe6e2; border-radius: 8px; }
.page-heading > span { gap: 10px; color: #3d805d; }
.page-heading > span > :first-child { font-size: 25px; }
.page-heading i { display: flex; flex-direction: column; font-style: normal; }
.page-heading small { font-size: 8px; color: #87938c; }
.page-heading strong { font-size: 14px; color: #28362f; }
.page-heading em { font-size: 8px; font-style: normal; color: #6d7972; }
.page-heading > div { gap: 7px; }
.metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 9px 0; }
.metric-grid article { gap: 10px; padding: 11px 13px; color: #3f805e; background: #fff; border: 1px solid #dfe6e2; border-radius: 7px; }
.metric-grid article.warning { color: #bf5a42; border-color: #edcfc5; }
.metric-grid article > :first-child { font-size: 21px; }
.metric-grid article span { display: flex; flex-direction: column; }
.metric-grid article strong { font-size: 16px; }
.metric-grid article small { color: #536159; }
.metric-grid article em { font-size: 8px; font-style: normal; color: #87938d; }
.blocker-alert { margin-bottom: 8px; }
.workspace-grid { display: grid; grid-template-columns: 245px minmax(0, 1fr); gap: 8px; min-height: 600px; }
.plan-list { padding: 10px; background: #fff; border: 1px solid #dfe6e2; border-radius: 8px; }
.plan-list > header { display: flex; justify-content: space-between; padding: 4px 5px 10px; }
.plan-list button { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 5px; width: 100%; padding: 9px; margin-bottom: 5px; color: #405048; text-align: left; cursor: pointer; background: #f8faf9; border: 1px solid #e2e7e4; border-radius: 6px; }
.plan-list button.active { background: #edf7f1; border-color: #9ccbb0; }
.plan-list button span { display: flex; flex-direction: column; min-width: 0; }
.plan-list button strong, .plan-list button small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.plan-list button small, .plan-list button em { color: #7e8a83; }
.plan-list button em { grid-column: 1 / -1; font-size: 10px; font-style: normal; }
.empty-workspace { display: grid; place-items: center; background: #fff; border: 1px solid #dfe6e2; border-radius: 8px; }
.sample-filter { width: 320px; margin: 12px 0; }
@media (max-width: 1100px) { .metric-grid { grid-template-columns: repeat(2, 1fr); } .workspace-grid { grid-template-columns: 1fr; } .plan-list { max-height: 240px; overflow: auto; } }
</style>
