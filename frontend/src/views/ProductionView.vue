<script setup lang="ts">
import {
  AlertOutlined,
  ApartmentOutlined,
  CheckCircleOutlined,
  DatabaseOutlined,
  DeploymentUnitOutlined,
  ReloadOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref } from 'vue'

import DatasetCatalogPanel from '@/components/production/DatasetCatalogPanel.vue'
import ProductionSchedulingPanel from '@/components/production/ProductionSchedulingPanel.vue'
import { useProductionStore } from '@/store/productionStore'
import { useUserStore } from '@/store/userStore'
import type {
  DatasetAssetCreatePayload,
  ProductionBatchCreatePayload,
  ProductionBatchStatus,
  WorkPackageCreatePayload,
  WorkPackageUpdatePayload,
} from '@/types/production'

const productionStore = useProductionStore()
const userStore = useUserStore()
const { overviewRef, loadingRef, savingRef } = storeToRefs(productionStore)
const activeTabRef = ref<string>('scheduling')
const datasetPanelRef = ref<InstanceType<typeof DatasetCatalogPanel> | null>(null)
const schedulingPanelRef = ref<InstanceType<typeof ProductionSchedulingPanel> | null>(null)

const canManageProductionComputed = computed<boolean>(() => (
  userStore.hasCapability('manage_production')
))
const canManageDatasetsComputed = computed<boolean>(() => (
  userStore.hasCapability('manage_datasets')
))
const operatorCodeComputed = computed<string | null>(() => (
  userStore.currentUserComputed?.user_code || null
))

const registerAsset = async (payload: DatasetAssetCreatePayload): Promise<void> => {
  try {
    await productionStore.registerAsset(payload)
    datasetPanelRef.value?.closeAfterSaved()
    message.success('多源数据资产已登记并写入来源与血缘审计')
  } catch {
    // 请求拦截器已显示安全错误。
  }
}

const createBatch = async (payload: ProductionBatchCreatePayload): Promise<void> => {
  try {
    await productionStore.createBatch(payload)
    schedulingPanelRef.value?.closeBatchModal()
    message.success('生产批次已创建并固化当前规则版本')
  } catch {
    // 请求拦截器已显示安全错误。
  }
}

const createPackages = async (
  batchCode: string,
  payload: WorkPackageCreatePayload,
): Promise<void> => {
  try {
    const result = await productionStore.createPackages(batchCode, payload)
    schedulingPanelRef.value?.closePackageModal()
    message.success(
      `已创建 ${result.created_count} 个县区作业包，显式关联 ${result.assigned_plot_count.toLocaleString()} 个任务图斑`,
    )
  } catch {
    // 请求拦截器已显示安全错误。
  }
}

const updateBatchStatus = async (
  batchCode: string,
  status: ProductionBatchStatus,
): Promise<void> => {
  const operatorCode = operatorCodeComputed.value
  if (!operatorCode) return
  try {
    await productionStore.updateBatchStatus(batchCode, status, operatorCode)
    message.success('生产批次状态已更新并写入审计')
  } catch {
    // 请求拦截器已显示安全错误。
  }
}

const updatePackage = async (
  packageCode: string,
  payload: WorkPackageUpdatePayload,
): Promise<void> => {
  try {
    await productionStore.updatePackage(packageCode, payload)
    schedulingPanelRef.value?.closePackageEditModal()
    message.success('作业包调度信息已更新并写入修改前后值')
  } catch {
    // 请求拦截器已显示安全错误。
  }
}

onMounted(() => {
  void productionStore.load()
})
</script>

<template>
  <div class="production-view">
    <header class="page-heading">
      <span><DeploymentUnitOutlined /><i><small>PRODUCTION CONTROL</small><strong>遥感生产调度中心</strong><em>多源数据、批次计划、县区分包与进度协调</em></i></span>
      <div>
        <a-tag color="green">{{ overviewRef?.work_areas.length || 0 }} 个县区工作区</a-tag>
        <a-button :loading="loadingRef" @click="productionStore.load"><ReloadOutlined /> 刷新</a-button>
      </div>
    </header>

    <a-spin :spinning="loadingRef">
      <template v-if="overviewRef">
        <section class="metric-grid">
          <article><DatabaseOutlined /><span><strong>{{ overviewRef.metrics.asset_count }}</strong><small>多源数据资产</small><em>{{ overviewRef.metrics.pending_asset_verification_count }} 项待实体核验</em></span></article>
          <article><DeploymentUnitOutlined /><span><strong>{{ overviewRef.metrics.active_batch_count }} / {{ overviewRef.metrics.batch_count }}</strong><small>活动 / 全部批次</small><em>按规则版本固化</em></span></article>
          <article><ApartmentOutlined /><span><strong>{{ overviewRef.metrics.package_count }}</strong><small>县区作业包</small><em>{{ overviewRef.metrics.assigned_plot_count.toLocaleString() }} 个显式图斑关联</em></span></article>
          <article :class="{ warning: overviewRef.metrics.overdue_package_count > 0 }"><AlertOutlined /><span><strong>{{ overviewRef.metrics.overdue_package_count }}</strong><small>逾期作业包</small><em>{{ overviewRef.metrics.completed_plot_count.toLocaleString() }} 个图斑已完成</em></span></article>
        </section>

        <a-alert
          v-if="!canManageProductionComputed && !canManageDatasetsComputed"
          class="permission-alert"
          type="info"
          show-icon
          message="当前身份为只读生产视图"
          description="批次、作业包和数据资产的创建与调度仅由项目负责人执行；独立监理可查看生产范围和进度证据。"
        />

        <section class="production-content">
          <a-tabs v-model:active-key="activeTabRef">
            <a-tab-pane key="scheduling">
              <template #tab><DeploymentUnitOutlined /> 生产调度</template>
              <ProductionSchedulingPanel
                ref="schedulingPanelRef"
                :overview="overviewRef"
                :users="userStore.usersRef"
                :saving="savingRef"
                :can-manage="canManageProductionComputed"
                :operator-code="operatorCodeComputed"
                @create-batch="createBatch"
                @create-packages="createPackages"
                @update-batch-status="updateBatchStatus"
                @update-package="updatePackage"
              />
            </a-tab-pane>
            <a-tab-pane key="datasets">
              <template #tab><DatabaseOutlined /> 多源数据目录</template>
              <DatasetCatalogPanel
                ref="datasetPanelRef"
                :assets="overviewRef.assets"
                :saving="savingRef"
                :can-manage="canManageDatasetsComputed"
                :operator-code="operatorCodeComputed"
                @register="registerAsset"
              />
            </a-tab-pane>
            <a-tab-pane key="rules">
              <template #tab><CheckCircleOutlined /> 当前批次规则</template>
              <div class="rule-snapshot">
                <a-empty v-if="!overviewRef.batches.length" description="创建生产批次后，这里将显示不可变规则快照" />
                <article v-for="batch in overviewRef.batches" :key="batch.batch_code">
                  <header><span><strong>{{ batch.batch_name }}</strong><small>{{ batch.batch_code }}</small></span><a-tag>规则 v{{ batch.rule_config_version }}</a-tag></header>
                  <dl>
                    <div v-for="(value, key) in batch.rule_profile_snapshot" :key="key"><dt>{{ key }}</dt><dd>{{ value ?? '未设置' }}</dd></div>
                  </dl>
                </article>
              </div>
            </a-tab-pane>
          </a-tabs>
        </section>
      </template>
    </a-spin>
  </div>
</template>

<style scoped>
.production-view { height: 100%; padding: 12px; overflow: auto; background: #f1f4f2; }
.page-heading, .page-heading > span, .page-heading > div, .metric-grid article, .rule-snapshot article header { display: flex; align-items: center; }
.page-heading { justify-content: space-between; padding: 13px 15px; background: #fff; border: 1px solid #dfe6e2; border-radius: 8px; }
.page-heading > span { gap: 10px; color: #3e8561; }
.page-heading > span > :first-child { font-size: 25px; }
.page-heading i { display: flex; flex-direction: column; font-style: normal; }
.page-heading small { font-size: 8px; color: #89958f; }
.page-heading strong { font-size: 14px; color: #29372f; }
.page-heading em { margin-top: 1px; font-size: 8px; font-style: normal; color: #69766f; }
.page-heading > div { gap: 7px; }
.metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 9px 0; }
.metric-grid article { gap: 10px; min-width: 0; padding: 11px 13px; color: #3f815e; background: #fff; border: 1px solid #dfe6e2; border-radius: 7px; }
.metric-grid article.warning { color: #c26043; border-color: #edcfc5; }
.metric-grid article > :first-child { flex: 0 0 auto; font-size: 21px; }
.metric-grid span { display: flex; flex-direction: column; min-width: 0; }
.metric-grid strong { font-size: 16px; }
.metric-grid small { font-size: 8px; color: #50635a; }
.metric-grid em { overflow: hidden; font-size: 7px; font-style: normal; color: #87938d; text-overflow: ellipsis; white-space: nowrap; }
.permission-alert { margin-bottom: 9px; }
.production-content { padding: 4px 14px 14px; background: #fff; border: 1px solid #dfe6e2; border-radius: 8px; }
.production-content :deep(.ant-tabs-nav) { margin-bottom: 12px; }
.rule-snapshot { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.rule-snapshot article { padding: 12px; background: #fafbfa; border: 1px solid #e1e7e3; border-radius: 7px; }
.rule-snapshot article header { justify-content: space-between; }
.rule-snapshot article header span { display: flex; flex-direction: column; }
.rule-snapshot article header strong { font-size: 10px; }
.rule-snapshot article header small { font-size: 8px; color: #849089; }
.rule-snapshot dl { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; }
.rule-snapshot dl div { min-width: 0; padding: 6px; background: #fff; border-radius: 4px; }
.rule-snapshot dt { overflow: hidden; font-size: 7px; color: #87948d; text-overflow: ellipsis; white-space: nowrap; }
.rule-snapshot dd { margin: 2px 0 0; overflow: hidden; font-size: 8px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 1100px) {
  .metric-grid { grid-template-columns: repeat(2, 1fr); }
  .rule-snapshot { grid-template-columns: 1fr; }
}
</style>
