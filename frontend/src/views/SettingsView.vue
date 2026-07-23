<script setup lang="ts">
import { SafetyCertificateOutlined, SettingOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref, watch } from 'vue'

import PlotAttributeFieldManager from '@/components/settings/PlotAttributeFieldManager.vue'
import { useRuleConfigStore } from '@/store/ruleConfigStore'
import { useUserStore } from '@/store/userStore'

const ruleConfigStore = useRuleConfigStore()
const userStore = useUserStore()
const { configRef, loadingRef, savingRef } = storeToRefs(ruleConfigStore)
const offsetThresholdRef = ref<number>(5)
const searchRadiusRef = ref<number>(1000)
const positionalPixelsRef = ref<number>(2)
const maxCaptureDaysRef = ref<number>(15)
const constructionMinAreaRef = ref<number>(200)
const otherAgriculturalMinAreaRef = ref<number>(400)
const completenessRateRef = ref<number>(98)
const boundaryAgreementRateRef = ref<number>(90)
const landClassAccuracyRef = ref<number>(90)
const keyFieldAccuracyRef = ref<number>(95)
const maxCloudCoverRef = ref<number | null>(null)
const outputCrsRef = ref<string>('EPSG:4490')
const outputProjectionRef = ref<string>('CGCS2000 高斯-克吕格（按成果分幅配置中央经线）')
const canManageRulesComputed = computed<boolean>(() => (
  userStore.hasCapability('manage_rules')
))

watch(
  configRef,
  (config) => {
    if (!config) return
    offsetThresholdRef.value = config.field_offset_threshold_m
    searchRadiusRef.value = config.field_search_radius_m
    positionalPixelsRef.value = config.positional_accuracy_pixels
    maxCaptureDaysRef.value = config.max_capture_image_days
    constructionMinAreaRef.value = config.construction_min_area_sqm
    otherAgriculturalMinAreaRef.value = config.other_agricultural_min_area_sqm
    completenessRateRef.value = config.completeness_rate_min
    boundaryAgreementRateRef.value = config.boundary_agreement_rate_min
    landClassAccuracyRef.value = config.land_class_accuracy_min
    keyFieldAccuracyRef.value = config.key_field_accuracy_min
    maxCloudCoverRef.value = config.max_cloud_cover_percent
    outputCrsRef.value = config.output_crs
    outputProjectionRef.value = config.output_projection
  },
  { immediate: true },
)

/**
 * 保存项目规则并由后端记录修改前后值。
 * Args:
 *   无。
 * Returns:
 *   Promise<void>: 保存和页面状态同步完成后结束。
 */
const saveRules = async (): Promise<void> => {
  if (searchRadiusRef.value <= offsetThresholdRef.value) {
    message.warning('最近邻搜索半径必须大于偏移判定阈值')
    return
  }
  if (otherAgriculturalMinAreaRef.value < constructionMinAreaRef.value) {
    message.warning('其他农用地最小图斑面积不得小于建设类阈值')
    return
  }
  const user = userStore.currentUserComputed
  if (!user || !canManageRulesComputed.value) {
    message.warning('当前项目身份无权修改业务规则')
    return
  }
  try {
    await ruleConfigStore.save({
      field_offset_threshold_m: offsetThresholdRef.value,
      field_search_radius_m: searchRadiusRef.value,
      positional_accuracy_pixels: positionalPixelsRef.value,
      max_capture_image_days: maxCaptureDaysRef.value,
      construction_min_area_sqm: constructionMinAreaRef.value,
      other_agricultural_min_area_sqm: otherAgriculturalMinAreaRef.value,
      completeness_rate_min: completenessRateRef.value,
      boundary_agreement_rate_min: boundaryAgreementRateRef.value,
      land_class_accuracy_min: landClassAccuracyRef.value,
      key_field_accuracy_min: keyFieldAccuracyRef.value,
      max_cloud_cover_percent: maxCloudCoverRef.value,
      output_crs: outputCrsRef.value,
      output_projection: outputProjectionRef.value,
      operator_code: user.user_code,
    })
    message.success('项目规则新版本已生效，后续生产批次将固化该版本')
  } catch {
    // 请求拦截器已显示后端安全错误，避免组件事件产生未捕获 Promise。
  }
}

onMounted(() => {
  void ruleConfigStore.load()
})
</script>

<template>
  <div class="settings-view">
    <header class="page-heading">
      <SettingOutlined />
      <span>
        <small>SYSTEM RULES</small>
        <strong>项目业务规则配置</strong>
        <em>阈值保存于数据库，并记录操作人和修改前后值</em>
      </span>
      <a-tag color="green">项目级配置</a-tag>
    </header>

    <a-spin :spinning="loadingRef">
      <section class="rule-section">
        <header>
          <span><SafetyCertificateOutlined /><strong>质量与内外业阈值</strong></span>
          <small>项目 {{ configRef?.project_code || 'RS-2026' }} · 规则 v{{ configRef?.version || 1 }}</small>
        </header>

        <a-alert
          v-if="!canManageRulesComputed"
          class="permission-alert"
          type="warning"
          show-icon
          message="当前身份仅可查看规则"
          description="只有项目负责人可以修改并发布项目级阈值。"
        />

        <div class="rule-grid">
          <label>
            <span><strong>外业点位偏移阈值</strong><small>点到图斑距离超过该值时标记为偏移</small></span>
            <a-input-number
              v-model:value="offsetThresholdRef"
              :min="0.1"
              :max="500"
              :step="0.5"
              :disabled="!canManageRulesComputed"
              addon-after="米"
            />
          </label>
          <label>
            <span><strong>最近邻搜索半径</strong><small>半径内没有有效图斑时标记为未匹配</small></span>
            <a-input-number
              v-model:value="searchRadiusRef"
              :min="1"
              :max="50000"
              :step="100"
              :disabled="!canManageRulesComputed"
              addon-after="米"
            />
          </label>
          <label>
            <span><strong>位置精度允许偏差</strong><small>配置控制点后用于边界位置精度检查</small></span>
            <a-input-number
              v-model:value="positionalPixelsRef"
              :min="0.1"
              :max="20"
              :step="0.5"
              :disabled="!canManageRulesComputed"
              addon-after="像元"
            />
          </label>
          <label>
            <span><strong>影像与外业最大时间差</strong><small>超过阈值将生成时间一致性疑点</small></span>
            <a-input-number
              v-model:value="maxCaptureDaysRef"
              :min="1"
              :max="365"
              :disabled="!canManageRulesComputed"
              addon-after="天"
            />
          </label>
        </div>

        <header class="sub-heading">
          <span><SafetyCertificateOutlined /><strong>遥感生产量化基线</strong></span>
          <small>来源：黑龙江省公开采购技术要求</small>
        </header>
        <div class="rule-grid production-rules">
          <label><span><strong>建设/设施农用地最小图斑</strong><small>小于阈值的候选变化不进入生产成果</small></span><a-input-number
            v-model:value="constructionMinAreaRef"
            :min="1"
            :max="1000000"
            :disabled="!canManageRulesComputed"
            addon-after="㎡"
          /></label>
          <label><span><strong>其他农用地最小图斑</strong><small>应不小于建设类最小图斑阈值</small></span><a-input-number
            v-model:value="otherAgriculturalMinAreaRef"
            :min="1"
            :max="1000000"
            :disabled="!canManageRulesComputed"
            addon-after="㎡"
          /></label>
          <label><span><strong>完整率下限</strong><small>采购基线不低于 98%</small></span><a-input-number
            v-model:value="completenessRateRef"
            :min="0"
            :max="100"
            :step="0.1"
            :disabled="!canManageRulesComputed"
            addon-after="%"
          /></label>
          <label><span><strong>边界吻合度下限</strong><small>采购基线不低于 90%</small></span><a-input-number
            v-model:value="boundaryAgreementRateRef"
            :min="0"
            :max="100"
            :step="0.1"
            :disabled="!canManageRulesComputed"
            addon-after="%"
          /></label>
          <label><span><strong>地类判定准确率下限</strong><small>采购基线不低于 90%</small></span><a-input-number
            v-model:value="landClassAccuracyRef"
            :min="0"
            :max="100"
            :step="0.1"
            :disabled="!canManageRulesComputed"
            addon-after="%"
          /></label>
          <label><span><strong>关键字段准确率下限</strong><small>采购基线不低于 95%</small></span><a-input-number
            v-model:value="keyFieldAccuracyRef"
            :min="0"
            :max="100"
            :step="0.1"
            :disabled="!canManageRulesComputed"
            addon-after="%"
          /></label>
          <label><span><strong>影像云量上限</strong><small>未设置时由具体任务规则包决定</small></span><a-input-number
            v-model:value="maxCloudCoverRef"
            :min="0"
            :max="100"
            :step="0.1"
            :disabled="!canManageRulesComputed"
            placeholder="未设置"
            addon-after="%"
          /></label>
          <label><span><strong>生产输出坐标系</strong><small>API 仍统一使用 EPSG:4326</small></span><a-input v-model:value="outputCrsRef" :disabled="!canManageRulesComputed" /></label>
          <label class="wide-rule"><span><strong>生产输出投影定义</strong><small>每次重投影必须记录转换证据</small></span><a-input v-model:value="outputProjectionRef" :disabled="!canManageRulesComputed" /></label>
        </div>

        <div class="save-bar">
          <span>
            <small>最近更新</small>
            <strong>{{ configRef?.updated_by || '--' }}</strong>
            <em>{{ configRef?.updated_at?.slice(0, 19).replace('T', ' ') || '--' }}</em>
          </span>
          <span class="current-operator">
            <small>当前操作身份</small>
            <strong>{{ userStore.currentUserComputed?.display_name || '--' }}</strong>
            <em>{{ userStore.currentUserComputed?.role_name || '--' }}</em>
          </span>
          <a-button
            type="primary"
            :loading="savingRef"
            :disabled="!canManageRulesComputed"
            @click="saveRules"
          >
            保存并生效
          </a-button>
        </div>
      </section>

      <PlotAttributeFieldManager :project-code="configRef?.project_code || 'RS-2026'" />

      <section class="workflow-section">
        <h3>审核流程</h3>
        <div><span>内业自检</span><a-tag color="green">启用</a-tag></div>
        <div><span>质检员审核</span><a-tag color="green">启用</a-tag></div>
        <div><span>甲方复核</span><a-tag color="green">启用</a-tag></div>
      </section>
    </a-spin>
  </div>
</template>

<style scoped>
.settings-view { width: 820px; max-width: calc(100% - 28px); margin: 14px auto; }
.page-heading { display: grid; grid-template-columns: 34px 1fr auto; gap: 10px; align-items: center; padding: 18px 20px; margin-bottom: 10px; color: #397d59; background: #fff; border: 1px solid #dfe6e2; border-radius: 8px; }
.page-heading > :first-child { font-size: 24px; }
.page-heading span, .save-bar span { display: flex; flex-direction: column; }
.page-heading small, .save-bar small, .rule-section header small, label small { font-size: 8px; color: #89958f; }
.page-heading strong { font-size: 15px; color: #28362f; }
.page-heading em { margin-top: 2px; font-size: 9px; font-style: normal; color: #66736c; }
.rule-section, .workflow-section { padding: 18px 20px; background: #fff; border: 1px solid #dfe6e2; border-radius: 8px; }
.rule-section > header { display: flex; align-items: center; justify-content: space-between; padding-bottom: 12px; border-bottom: 1px solid #e5e9e7; }
.rule-section > header span { display: flex; gap: 7px; align-items: center; color: #397d59; }
.rule-section > header strong, .workflow-section h3 { font-size: 12px; color: #2d3a33; }
.rule-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 14px 0; }
.sub-heading { margin-top: 4px; padding-top: 14px !important; border-top: 1px solid #e5e9e7; }
.production-rules { padding-top: 10px; }
.wide-rule { grid-column: 1 / -1; }
.permission-alert { margin-top: 12px; }
.rule-grid label { display: grid; grid-template-columns: minmax(0, 1fr) 170px; gap: 12px; align-items: center; padding: 12px; background: #f7f9f8; border: 1px solid #e8edea; border-radius: 6px; }
.rule-grid label > span { display: flex; flex-direction: column; }
.rule-grid label strong { font-size: 10px; }
.rule-grid :deep(.ant-input-number-group-wrapper) { width: 100%; }
.save-bar { display: grid; grid-template-columns: 1fr 170px auto; gap: 8px; align-items: center; padding-top: 12px; border-top: 1px solid #e5e9e7; }
.save-bar strong { font-size: 10px; }
.save-bar em { font-size: 8px; font-style: normal; color: #7b8781; }
.current-operator { padding-left: 10px; border-left: 2px solid #dfe7e2; }
.workflow-section { margin-top: 10px; }
.workflow-section > div { display: flex; align-items: center; justify-content: space-between; padding: 10px; font-size: 9px; background: #f7f9f8; border-bottom: 1px solid #edf0ee; }
@media (max-width: 900px) {
  .rule-grid { grid-template-columns: 1fr; }
  .wide-rule { grid-column: auto; }
  .save-bar { grid-template-columns: 1fr; }
}
</style>
