<script setup lang="ts">
import {
  CalendarOutlined,
  DeploymentUnitOutlined,
  EditOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  TeamOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { computed, ref, watch } from 'vue'

import type {
  ProductionBatch,
  ProductionBatchCreatePayload,
  ProductionBatchStatus,
  ProductionOverview,
  ReconciliationStatus,
  WorkPackage,
  WorkPackageCreatePayload,
  WorkPackageStatus,
  WorkPackageUpdatePayload,
} from '@/types/production'
import type { ProjectUser } from '@/types/workbench'

const props = defineProps<{
  overview: ProductionOverview
  users: ProjectUser[]
  saving: boolean
  canManage: boolean
  operatorCode: string | null
}>()

const emit = defineEmits<{
  createBatch: [payload: ProductionBatchCreatePayload]
  createPackages: [batchCode: string, payload: WorkPackageCreatePayload]
  updateBatchStatus: [batchCode: string, status: ProductionBatchStatus]
  updatePackage: [packageCode: string, payload: WorkPackageUpdatePayload]
}>()

const selectedBatchCodeRef = ref<string>('')
const batchModalOpenRef = ref<boolean>(false)
const packageModalOpenRef = ref<boolean>(false)
const editPackageModalOpenRef = ref<boolean>(false)
const editingPackageRef = ref<WorkPackage | null>(null)

const batchCodeRef = ref<string>('')
const batchNameRef = ref<string>('')
const sourceAssetCodeRef = ref<string | undefined>(undefined)
const targetAssetCodeRef = ref<string | undefined>(undefined)
const batchStartRef = ref<string>('')
const batchEndRef = ref<string>('')

const regionCodesRef = ref<string[]>([])
const assigneeCodeRef = ref<string>('')
const packageDeadlineRef = ref<string>('')

const editAssigneeCodeRef = ref<string>('')
const editDeadlineRef = ref<string>('')
const editStatusRef = ref<WorkPackageStatus>('pending')
const editReconciliationRef = ref<ReconciliationStatus>('pending')

const imageryAssetsComputed = computed(() => (
  props.overview.assets.filter((asset) => asset.asset_type === 'imagery')
))

const selectedBatchComputed = computed<ProductionBatch | null>(() => (
  props.overview.batches.find((batch) => batch.batch_code === selectedBatchCodeRef.value)
  || props.overview.batches[0]
  || null
))

const availableWorkAreasComputed = computed(() => {
  const batchCode = selectedBatchComputed.value?.batch_code
  return props.overview.work_areas.filter((area) => (
    area.plot_count > 0 && (!batchCode || !area.assigned_batch_codes.includes(batchCode))
  ))
})

const workAreasByCityComputed = computed(() => {
  const groups = new Map<string, typeof props.overview.work_areas>()
  availableWorkAreasComputed.value.forEach((area) => {
    const items = groups.get(area.city_name) || []
    items.push(area)
    groups.set(area.city_name, items)
  })
  return Array.from(groups.entries())
})

const assigneeOptionsComputed = computed(() => props.users.filter((user) => (
  user.role_code === 'interpreter'
  || user.role_code === 'quality_inspector'
  || user.role_code === 'project_manager'
)))

const statusLabels: Record<ProductionBatchStatus, string> = {
  draft: '草稿',
  planned: '已计划',
  in_progress: '生产中',
  reconciling: '合并校核',
  completed: '已完成',
  cancelled: '已取消',
}

const packageStatusLabels: Record<WorkPackageStatus, string> = {
  pending: '待开始',
  in_progress: '处理中',
  blocked: '阻塞',
  completed: '已完成',
}

const reconciliationLabels: Record<ReconciliationStatus, string> = {
  pending: '待校核',
  checking: '校核中',
  passed: '已通过',
  conflict: '存在冲突',
}

const packageTransitions: Record<WorkPackageStatus, WorkPackageStatus[]> = {
  pending: ['in_progress', 'blocked'],
  in_progress: ['blocked', 'completed'],
  blocked: ['in_progress'],
  completed: [],
}

const reconciliationTransitions: Record<ReconciliationStatus, ReconciliationStatus[]> = {
  pending: ['checking'],
  checking: ['passed', 'conflict'],
  conflict: ['checking'],
  passed: [],
}

const packageStatusDisabled = (status: WorkPackageStatus): boolean => {
  const current = editingPackageRef.value
  if (!current || status === current.status) return false
  if (!packageTransitions[current.status].includes(status)) return true
  return status === 'completed'
    && (current.progress < 100 || editReconciliationRef.value !== 'passed')
}

const reconciliationStatusDisabled = (status: ReconciliationStatus): boolean => {
  const current = editingPackageRef.value
  if (!current || status === current.reconciliation_status) return false
  return !reconciliationTransitions[current.reconciliation_status].includes(status)
}

const batchStatusColor = (status: ProductionBatchStatus): string => {
  if (status === 'completed') return 'green'
  if (status === 'in_progress' || status === 'reconciling') return 'blue'
  if (status === 'cancelled') return 'default'
  return 'orange'
}

const packageStatusColor = (status: WorkPackageStatus): string => {
  if (status === 'completed') return 'green'
  if (status === 'blocked') return 'red'
  if (status === 'in_progress') return 'blue'
  return 'orange'
}

const nextBatchAction = (
  batch: ProductionBatch,
): { label: string; status: ProductionBatchStatus } | null => {
  if (batch.status === 'planned') return { label: '开始生产', status: 'in_progress' }
  if (batch.status === 'in_progress') return { label: '进入合并校核', status: 'reconciling' }
  if (batch.status === 'reconciling') return { label: '确认批次完成', status: 'completed' }
  return null
}

const openCreateBatch = (): void => {
  if (!props.canManage) {
    message.warning('当前项目身份无权创建生产批次')
    return
  }
  batchModalOpenRef.value = true
}

const submitBatch = (): void => {
  if (!props.operatorCode) {
    message.warning('当前项目身份尚未初始化')
    return
  }
  if (!batchCodeRef.value.trim() || !batchNameRef.value.trim()) {
    message.warning('请填写批次编号和名称')
    return
  }
  if (!batchStartRef.value || !batchEndRef.value) {
    message.warning('请选择完整的生产计划周期')
    return
  }
  if (batchEndRef.value < batchStartRef.value) {
    message.warning('计划结束日期不得早于开始日期')
    return
  }
  emit('createBatch', {
    batch_code: batchCodeRef.value.trim(),
    batch_name: batchNameRef.value.trim(),
    source_asset_code: sourceAssetCodeRef.value || null,
    target_asset_code: targetAssetCodeRef.value || null,
    planned_start_date: batchStartRef.value,
    planned_end_date: batchEndRef.value,
    operator_code: props.operatorCode,
  })
}

const openCreatePackages = (): void => {
  if (!selectedBatchComputed.value) {
    message.warning('请先创建并选择生产批次')
    return
  }
  if (!props.canManage) {
    message.warning('当前项目身份无权拆分作业包')
    return
  }
  regionCodesRef.value = []
  assigneeCodeRef.value = assigneeOptionsComputed.value[0]?.user_code || ''
  packageDeadlineRef.value = selectedBatchComputed.value.planned_end_date
  packageModalOpenRef.value = true
}

const submitPackages = (): void => {
  const batch = selectedBatchComputed.value
  if (!batch || !props.operatorCode) return
  if (!regionCodesRef.value.length || !assigneeCodeRef.value || !packageDeadlineRef.value) {
    message.warning('请选择县区、负责人和作业期限')
    return
  }
  emit('createPackages', batch.batch_code, {
    region_codes: regionCodesRef.value,
    assignee_code: assigneeCodeRef.value,
    deadline: packageDeadlineRef.value,
    operator_code: props.operatorCode,
  })
}

const openEditPackage = (workPackage: WorkPackage): void => {
  if (!props.canManage) return
  editingPackageRef.value = workPackage
  editAssigneeCodeRef.value = workPackage.assignee_code
  editDeadlineRef.value = workPackage.deadline
  editStatusRef.value = workPackage.status
  editReconciliationRef.value = workPackage.reconciliation_status
  editPackageModalOpenRef.value = true
}

const submitPackageEdit = (): void => {
  const workPackage = editingPackageRef.value
  if (!workPackage || !props.operatorCode) return
  if (
    editStatusRef.value === 'completed'
    && (workPackage.progress < 100 || editReconciliationRef.value !== 'passed')
  ) {
    message.warning('图斑未全部解译或合并校核未通过，不能标记完成')
    return
  }
  emit('updatePackage', workPackage.package_code, {
    assignee_code: editAssigneeCodeRef.value,
    deadline: editDeadlineRef.value,
    status: editStatusRef.value,
    reconciliation_status: editReconciliationRef.value,
    operator_code: props.operatorCode,
  })
}

const runBatchAction = (batch: ProductionBatch): void => {
  const action = nextBatchAction(batch)
  if (!action || !props.operatorCode) return
  emit('updateBatchStatus', batch.batch_code, action.status)
}

watch(
  () => props.overview.batches,
  (batches) => {
    if (!batches.length) {
      selectedBatchCodeRef.value = ''
      return
    }
    if (!batches.some((item) => item.batch_code === selectedBatchCodeRef.value)) {
      selectedBatchCodeRef.value = batches[0].batch_code
    }
  },
  { immediate: true },
)

defineExpose({
  closeBatchModal: () => {
    batchModalOpenRef.value = false
    batchCodeRef.value = ''
    batchNameRef.value = ''
    sourceAssetCodeRef.value = undefined
    targetAssetCodeRef.value = undefined
    batchStartRef.value = ''
    batchEndRef.value = ''
  },
  closePackageModal: () => {
    packageModalOpenRef.value = false
  },
  closePackageEditModal: () => {
    editPackageModalOpenRef.value = false
  },
})
</script>

<template>
  <section class="scheduling-panel">
    <header class="panel-heading">
      <span><DeploymentUnitOutlined /><i><small>PRODUCTION SCHEDULING</small><strong>生产批次与县区作业包</strong></i></span>
      <div>
        <a-button @click="openCreatePackages"><TeamOutlined /> 县区拆包</a-button>
        <a-button type="primary" :disabled="!canManage" @click="openCreateBatch"><PlusOutlined /> 新建批次</a-button>
      </div>
    </header>

    <a-empty
      v-if="!overview.batches.length"
      class="empty-state"
      description="尚未建立生产批次；创建批次后可按真实县区固化任务图斑范围、负责人和期限"
    >
      <a-button type="primary" :disabled="!canManage" @click="openCreateBatch">创建首个生产批次</a-button>
    </a-empty>

    <template v-else>
      <div class="batch-selector">
        <button
          v-for="batch in overview.batches"
          :key="batch.batch_code"
          :class="{ active: selectedBatchComputed?.batch_code === batch.batch_code }"
          @click="selectedBatchCodeRef = batch.batch_code"
        >
          <span><strong>{{ batch.batch_name }}</strong><small>{{ batch.batch_code }}</small></span>
          <a-tag :color="batchStatusColor(batch.status)">{{ statusLabels[batch.status] }}</a-tag>
          <em>{{ batch.package_count }} 包 · {{ batch.progress.toFixed(1) }}%</em>
        </button>
      </div>

      <article v-if="selectedBatchComputed" class="batch-detail">
        <header>
          <span>
            <strong>{{ selectedBatchComputed.batch_name }}</strong>
            <small>{{ selectedBatchComputed.batch_code }} · 规则 v{{ selectedBatchComputed.rule_config_version }}</small>
          </span>
          <a-button
            v-if="nextBatchAction(selectedBatchComputed)"
            type="primary"
            size="small"
            :loading="saving"
            :disabled="!canManage"
            @click="runBatchAction(selectedBatchComputed)"
          >
            <PlayCircleOutlined /> {{ nextBatchAction(selectedBatchComputed)?.label }}
          </a-button>
        </header>
        <div class="batch-meta">
          <span><CalendarOutlined /> {{ selectedBatchComputed.planned_start_date }} 至 {{ selectedBatchComputed.planned_end_date }}</span>
          <span>前时相：{{ selectedBatchComputed.source_asset_code || '未绑定' }}</span>
          <span>后时相：{{ selectedBatchComputed.target_asset_code || '未绑定' }}</span>
          <span>创建人：{{ selectedBatchComputed.created_by }}</span>
        </div>
        <a-progress :percent="selectedBatchComputed.progress" :show-info="false" stroke-color="#4a9b70" />

        <div class="package-table">
          <header class="table-row table-head">
            <span>县区作业包</span><span>负责人 / 期限</span><span>显式图斑范围</span><span>进度</span><span>校核 / 状态</span><span>操作</span>
          </header>
          <div v-if="!selectedBatchComputed.packages.length" class="package-empty">
            当前批次尚未拆分县区作业包
          </div>
          <div
            v-for="workPackage in selectedBatchComputed.packages"
            :key="workPackage.package_code"
            class="table-row"
            :class="{ overdue: workPackage.overdue }"
          >
            <span><strong>{{ workPackage.region_name }}</strong><small>{{ workPackage.package_code }}</small></span>
            <span><strong>{{ workPackage.assignee_name }}</strong><small :class="{ danger: workPackage.overdue }">{{ workPackage.deadline }}{{ workPackage.overdue ? ' · 已逾期' : '' }}</small></span>
            <span><strong>{{ workPackage.active_plot_count.toLocaleString() }} 图斑</strong><small>{{ workPackage.planned_area_ha.toFixed(2) }} 公顷</small></span>
            <span><strong>{{ workPackage.completed_plot_count }} / {{ workPackage.active_plot_count }}</strong><a-progress :percent="workPackage.progress" :show-info="false" size="small" /></span>
            <span><a-tag>{{ reconciliationLabels[workPackage.reconciliation_status] }}</a-tag><a-tag :color="packageStatusColor(workPackage.status)">{{ packageStatusLabels[workPackage.status] }}</a-tag></span>
            <span><a-button size="small" :disabled="!canManage" @click="openEditPackage(workPackage)"><EditOutlined /> 调度</a-button></span>
          </div>
        </div>
      </article>
    </template>

    <a-modal
      v-model:open="batchModalOpenRef"
      title="新建遥感生产批次"
      width="640px"
      :confirm-loading="saving"
      ok-text="创建批次"
      @ok="submitBatch"
    >
      <a-alert
        type="info"
        show-icon
        message="批次创建时固化当前项目规则版本"
        description="后续规则调整不会静默改变既有批次；前后时相影像可暂不绑定，但会作为生产阻断信息明确显示。"
      />
      <div class="form-grid">
        <label><span>批次编号</span><a-input v-model:value="batchCodeRef" placeholder="如 HLJ-2026-07-A" /></label>
        <label><span>批次名称</span><a-input v-model:value="batchNameRef" /></label>
        <label><span>前时相影像</span><a-select v-model:value="sourceAssetCodeRef" allow-clear placeholder="可选"><a-select-option v-for="asset in imageryAssetsComputed" :key="asset.asset_code" :value="asset.asset_code">{{ asset.asset_code }} · {{ asset.asset_name }}</a-select-option></a-select></label>
        <label><span>后时相影像</span><a-select v-model:value="targetAssetCodeRef" allow-clear placeholder="可选"><a-select-option v-for="asset in imageryAssetsComputed" :key="asset.asset_code" :value="asset.asset_code">{{ asset.asset_code }} · {{ asset.asset_name }}</a-select-option></a-select></label>
        <label><span>计划开始</span><input v-model="batchStartRef" type="date"></label>
        <label><span>计划结束</span><input v-model="batchEndRef" type="date"></label>
      </div>
    </a-modal>

    <a-modal
      v-model:open="packageModalOpenRef"
      title="按真实县区创建作业包"
      width="700px"
      :confirm-loading="saving"
      ok-text="固化图斑范围并创建"
      @ok="submitPackages"
    >
      <a-alert
        type="warning"
        show-icon
        message="每个作业包将显式写入当前任务图斑"
        description="面积和图斑量由数据库实时计算，县区名称不会被用作后续范围推断。没有任务图斑的县区不会出现在可选列表。"
      />
      <div class="package-form">
        <label><span>目标批次</span><strong>{{ selectedBatchComputed?.batch_name || '--' }}</strong></label>
        <label><span>县区范围</span><a-select
          v-model:value="regionCodesRef"
          mode="multiple"
          show-search
          :max-tag-count="4"
          placeholder="可多选县区"
        ><a-select-opt-group v-for="group in workAreasByCityComputed" :key="group[0]" :label="group[0]"><a-select-option v-for="area in group[1]" :key="area.region_code" :value="area.region_code">{{ area.region_name }} · {{ area.plot_count }} 图斑 · {{ area.area_ha.toFixed(2) }} 公顷</a-select-option></a-select-opt-group></a-select></label>
        <label><span>负责人</span><a-select v-model:value="assigneeCodeRef"><a-select-option v-for="user in assigneeOptionsComputed" :key="user.user_code" :value="user.user_code">{{ user.display_name }} · {{ user.role_name }}</a-select-option></a-select></label>
        <label><span>作业期限</span><input v-model="packageDeadlineRef" type="date"></label>
      </div>
    </a-modal>

    <a-modal
      v-model:open="editPackageModalOpenRef"
      title="作业包调度"
      width="560px"
      :confirm-loading="saving"
      ok-text="保存调度"
      @ok="submitPackageEdit"
    >
      <div v-if="editingPackageRef" class="edit-package-summary">
        <strong>{{ editingPackageRef.region_name }}</strong>
        <span>{{ editingPackageRef.completed_plot_count }} / {{ editingPackageRef.active_plot_count }} 图斑 · {{ editingPackageRef.progress.toFixed(2) }}%</span>
      </div>
      <div class="package-form">
        <label><span>负责人</span><a-select v-model:value="editAssigneeCodeRef"><a-select-option v-for="user in assigneeOptionsComputed" :key="user.user_code" :value="user.user_code">{{ user.display_name }} · {{ user.role_name }}</a-select-option></a-select></label>
        <label><span>作业期限</span><input v-model="editDeadlineRef" type="date"></label>
        <label><span>作业状态</span><a-select v-model:value="editStatusRef"><a-select-option value="pending" :disabled="packageStatusDisabled('pending')">待开始</a-select-option><a-select-option value="in_progress" :disabled="packageStatusDisabled('in_progress')">处理中</a-select-option><a-select-option value="blocked" :disabled="packageStatusDisabled('blocked')">阻塞</a-select-option><a-select-option value="completed" :disabled="packageStatusDisabled('completed')">已完成</a-select-option></a-select></label>
        <label><span>合并校核</span><a-select v-model:value="editReconciliationRef"><a-select-option value="pending" :disabled="reconciliationStatusDisabled('pending')">待校核</a-select-option><a-select-option value="checking" :disabled="reconciliationStatusDisabled('checking')">校核中</a-select-option><a-select-option value="passed" :disabled="reconciliationStatusDisabled('passed')">已通过</a-select-option><a-select-option value="conflict" :disabled="reconciliationStatusDisabled('conflict')">存在冲突</a-select-option></a-select></label>
      </div>
    </a-modal>
  </section>
</template>

<style scoped>
.scheduling-panel { min-height: 420px; }
.panel-heading, .panel-heading > span, .panel-heading > div, .batch-detail > header, .batch-meta { display: flex; align-items: center; }
.panel-heading { justify-content: space-between; margin-bottom: 10px; }
.panel-heading > span { gap: 9px; color: #3f8662; }
.panel-heading > span > :first-child { font-size: 22px; }
.panel-heading i { display: flex; flex-direction: column; font-style: normal; }
.panel-heading small { font-size: 8px; color: #89958f; }
.panel-heading strong { font-size: 13px; color: #29372f; }
.panel-heading > div { gap: 7px; }
.empty-state { padding: 70px 20px; background: #fafbfa; border: 1px dashed #d9e1dc; border-radius: 7px; }
.batch-selector { display: flex; gap: 6px; padding-bottom: 9px; overflow-x: auto; }
.batch-selector button { display: grid; grid-template-columns: minmax(120px, 1fr) auto; gap: 3px 8px; min-width: 220px; padding: 9px 10px; text-align: left; background: #f8faf9; border: 1px solid #dfe6e2; border-radius: 6px; }
.batch-selector button.active { background: #eef6f1; border-color: #70aa87; box-shadow: inset 3px 0 #4d9b70; }
.batch-selector span { display: flex; flex-direction: column; min-width: 0; }
.batch-selector strong { overflow: hidden; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.batch-selector small, .batch-selector em { font-size: 7px; font-style: normal; color: #7c8982; }
.batch-selector em { grid-column: 1 / -1; }
.batch-detail { padding: 12px; background: #fafbfa; border: 1px solid #dfe6e2; border-radius: 7px; }
.batch-detail > header { justify-content: space-between; }
.batch-detail > header > span { display: flex; flex-direction: column; }
.batch-detail > header strong { font-size: 12px; }
.batch-detail > header small { font-size: 8px; color: #7d8a83; }
.batch-meta { flex-wrap: wrap; gap: 6px 14px; padding: 8px 0; font-size: 8px; color: #66746d; }
.package-table { margin-top: 10px; overflow-x: auto; background: #fff; border: 1px solid #e3e9e5; border-radius: 6px; }
.table-row { display: grid; grid-template-columns: 1.35fr 1.15fr 1fr 1fr 1fr 70px; gap: 8px; align-items: center; min-width: 900px; padding: 9px 10px; border-bottom: 1px solid #edf0ee; }
.table-row.overdue { background: #fff8f5; }
.table-head { font-size: 8px; font-weight: 600; color: #74817a; background: #f4f7f5; }
.table-row > span { display: flex; flex-direction: column; min-width: 0; }
.table-row > span:nth-last-child(2) { flex-direction: row; flex-wrap: wrap; }
.table-row strong { overflow: hidden; font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }
.table-row small { font-size: 7px; color: #7e8b84; }
.table-row small.danger { color: #c45f45; }
.package-empty { padding: 40px; font-size: 9px; color: #87948d; text-align: center; }
.form-grid, .package-form { display: grid; gap: 10px; margin-top: 14px; }
.form-grid { grid-template-columns: 1fr 1fr; }
.form-grid label, .package-form label { display: grid; grid-template-columns: 84px minmax(0, 1fr); gap: 8px; align-items: center; font-size: 9px; }
input[type='date'] { width: 100%; height: 32px; padding: 0 9px; font: inherit; color: #27352e; background: #fff; border: 1px solid #d9d9d9; border-radius: 6px; }
.edit-package-summary { display: flex; justify-content: space-between; padding: 10px; color: #3c7457; background: #f0f6f2; border-radius: 6px; }
.edit-package-summary span { font-size: 8px; }
@media (max-width: 900px) {
  .form-grid { grid-template-columns: 1fr; }
}
</style>
