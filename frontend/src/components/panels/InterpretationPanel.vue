<script setup lang="ts">
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed } from 'vue'

import TaskQualityPanel from '@/components/quality/TaskQualityPanel.vue'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type { PlotAttributeUpdate, QualityRuleResult } from '@/types/workbench'
import { formatArea, hectaresToMu } from '@/utils/area'

const workbenchStore = useWorkbenchStore()
const {
  plotAttributesRef,
  plotDraftRef,
  plotVersionsRef,
  plotDirtyComputed,
  canEditPlotsComputed,
  canRunPlotQualityComputed,
  savingPlotRef,
  qualityCheckingRef,
  qualityResultRef,
} = storeToRefs(workbenchStore)

const landClassOptions = ['耕地', '园地', '林地', '草地', '水域', '建设用地']
const cropTypeOptions = ['水稻', '玉米', '小麦', '大豆', '马铃薯', '蔬菜']
const plantingModeOptions = ['单季种植', '复种', '轮作', '间作', '设施种植']
const irrigationOptions = ['良好', '一般', '较差', '无灌排设施']

const cropRequiredComputed = computed<boolean>(
  () => plotDraftRef.value?.land_class === '耕地',
)

const updateDraft = <TKey extends keyof PlotAttributeUpdate>(
  key: TKey,
  value: PlotAttributeUpdate[TKey],
): void => {
  workbenchStore.updatePlotDraft({ [key]: value })
  if (key === 'land_class' && value !== '耕地') {
    workbenchStore.updatePlotDraft({ crop_type: null })
  }
}

const savePlot = async (): Promise<void> => {
  if (!canEditPlotsComputed.value) {
    message.warning('当前项目身份无权编辑图斑属性')
    return
  }
  if (!plotDraftRef.value?.land_class) {
    message.warning('请选择一级地类')
    return
  }
  if (cropRequiredComputed.value && !plotDraftRef.value.crop_type) {
    message.warning('耕地图斑必须选择作物类型')
    return
  }
  const attributes = await workbenchStore.saveSelectedPlot()
  message.success(`图斑 ${attributes.plot_code} 已保存为 v${attributes.version}`)
}

const runQualityCheck = async (): Promise<void> => {
  if (!canRunPlotQualityComputed.value) {
    message.warning('当前项目身份无权执行图斑质量检查')
    return
  }
  if (plotDirtyComputed.value) {
    message.warning('请先保存属性修改，再执行质量检查')
    return
  }
  try {
    const result = await workbenchStore.checkSelectedPlotQuality()
    if (result.can_submit) {
      message.success(`质量检查完成，得分 ${result.score}`)
    } else {
      message.warning(`质量检查发现阻断项，当前得分 ${result.score}`)
    }
  } catch {
    // 请求拦截器已经显示后端安全错误，避免事件处理器产生未捕获 Promise。
  }
}

const statusColor = (rule: QualityRuleResult): string => ({
  pass: 'success',
  warning: 'warning',
  fail: 'error',
}[rule.status])

const statusLabel = (rule: QualityRuleResult): string => ({
  pass: '通过',
  warning: rule.rule_code === 'POSITIONAL_ACCURACY_CONFIG' ? '待配置' : '警告',
  fail: '不通过',
}[rule.status])
</script>

<template>
  <section class="panel">
    <TaskQualityPanel />
    <header>
      <span>
        <small>当前解译图斑</small>
        <strong>{{ plotAttributesRef?.plot_code || '未选择' }}</strong>
      </span>
      <a-space size="small">
        <a-badge v-if="plotDirtyComputed" status="processing" text="未保存" />
        <a-tag color="green">v{{ plotAttributesRef?.version || 1 }}</a-tag>
      </a-space>
    </header>

    <div class="geometry-grid">
      <div><small>面积</small><strong>{{ formatArea(plotAttributesRef?.area_ha) }}</strong><span>公顷</span></div>
      <div><small>折合面积</small><strong>{{ plotAttributesRef?.area_ha ? formatArea(hectaresToMu(plotAttributesRef.area_ha)) : '--' }}</strong><span>亩</span></div>
      <div class="village"><small>权属村</small><strong>{{ plotAttributesRef?.owner_village || '--' }}</strong></div>
      <div class="village">
        <small>行政层级</small>
        <strong>
          {{ [plotAttributesRef?.province_name, plotAttributesRef?.city_name, plotAttributesRef?.district_name].filter(Boolean).join(' / ') || '--' }}
        </strong>
      </div>
    </div>

    <div v-if="plotAttributesRef?.source_name" class="source-card">
      <span>
        <small>边界数据来源</small>
        <strong>{{ plotAttributesRef.source_name }}</strong>
      </span>
      <a
        v-if="plotAttributesRef.source_uri"
        :href="plotAttributesRef.source_uri"
        target="_blank"
        rel="noopener noreferrer"
      >查看原始要素</a>
      <p>
        要素 {{ plotAttributesRef.source_feature_id || '--' }}
        · 版本 {{ plotAttributesRef.source_version || '--' }}
        · {{ plotAttributesRef.source_updated_at?.slice(0, 10) || '日期未知' }}
      </p>
    </div>

    <a-empty v-if="!plotDraftRef" description="请在地图上选择一个图斑" />
    <template v-else>
      <div class="attribute-form">
        <h3>地类与种植属性</h3>
        <label>
          <span>一级地类 <b>*</b></span>
          <a-select
            :value="plotDraftRef.land_class || undefined"
            :disabled="!canEditPlotsComputed"
            placeholder="请选择地类"
            @change="(value: string) => updateDraft('land_class', value)"
          >
            <a-select-option v-for="item in landClassOptions" :key="item" :value="item">{{ item }}</a-select-option>
          </a-select>
        </label>
        <label>
          <span>作物类型 <b v-if="cropRequiredComputed">*</b></span>
          <a-select
            allow-clear
            :disabled="!cropRequiredComputed || !canEditPlotsComputed"
            :value="plotDraftRef.crop_type || undefined"
            :placeholder="cropRequiredComputed ? '请选择作物' : '非耕地不适用'"
            @change="(value: string | undefined) => updateDraft('crop_type', value || null)"
          >
            <a-select-option v-for="item in cropTypeOptions" :key="item" :value="item">{{ item }}</a-select-option>
          </a-select>
        </label>
        <label>
          <span>种植模式</span>
          <a-select
            allow-clear
            :value="plotDraftRef.planting_mode || undefined"
            :disabled="!canEditPlotsComputed"
            placeholder="请选择种植模式"
            @change="(value: string | undefined) => updateDraft('planting_mode', value || null)"
          >
            <a-select-option v-for="item in plantingModeOptions" :key="item" :value="item">{{ item }}</a-select-option>
          </a-select>
        </label>
        <label>
          <span>灌排条件</span>
          <a-select
            allow-clear
            :value="plotDraftRef.irrigation_condition || undefined"
            :disabled="!canEditPlotsComputed"
            placeholder="请选择灌排条件"
            @change="(value: string | undefined) => updateDraft('irrigation_condition', value || null)"
          >
            <a-select-option v-for="item in irrigationOptions" :key="item" :value="item">{{ item }}</a-select-option>
          </a-select>
        </label>
        <div class="status-row">
          <span>解译状态</span>
          <a-tag color="blue">{{ plotAttributesRef?.interpretation_status || 'interpreting' }}</a-tag>
        </div>
      </div>

      <div class="actions">
        <a-button
          :disabled="!plotDirtyComputed || !canEditPlotsComputed"
          @click="workbenchStore.resetPlotDraft()"
        >
          撤销修改
        </a-button>
        <a-button
          type="primary"
          :loading="savingPlotRef"
          :disabled="!plotDirtyComputed || !canEditPlotsComputed"
          @click="savePlot"
        >
          保存属性
        </a-button>
        <a-button
          :loading="qualityCheckingRef"
          :disabled="plotDirtyComputed || !canRunPlotQualityComputed"
          @click="runQualityCheck"
        >
          质量检查
        </a-button>
      </div>

      <section v-if="qualityResultRef" class="quality-card">
        <div class="quality-heading">
          <span><small>质量得分</small><strong>{{ qualityResultRef.score }}</strong></span>
          <a-tag :color="qualityResultRef.can_submit ? 'success' : 'error'">
            {{ qualityResultRef.can_submit ? '允许提交' : '需要整改' }}
          </a-tag>
        </div>
        <a-progress :percent="qualityResultRef.score" :show-info="false" :status="qualityResultRef.can_submit ? 'success' : 'exception'" />
        <div class="quality-coverage">
          <span>检查覆盖 {{ qualityResultRef.checked_plot_count }} / {{ qualityResultRef.total_plot_count }}</span>
          <span>门禁通过 {{ qualityResultRef.passing_plot_count }} / {{ qualityResultRef.total_plot_count }}</span>
        </div>
        <ul>
          <li v-for="rule in qualityResultRef.rules" :key="rule.rule_code">
            <div>
              <strong>{{ rule.label }}</strong>
              <span>
                <a-tag v-if="rule.blocking && rule.status !== 'pass'" color="error">阻断项</a-tag>
                <a-tag :color="statusColor(rule)">{{ statusLabel(rule) }}</a-tag>
              </span>
            </div>
            <p>{{ rule.detail }}</p>
          </li>
        </ul>
      </section>

      <div class="version-summary">
        历史版本 {{ plotVersionsRef?.versions.length || 0 }} 个，当前版本 v{{ plotVersionsRef?.current_version || plotAttributesRef?.version || 1 }}
      </div>
    </template>
  </section>
</template>

<style scoped lang="less">
.panel { height: 100%; padding: 14px; overflow: auto; }
header { display: flex; align-items: center; justify-content: space-between; }
header > span { display: flex; flex-direction: column; }
small { font-size: 9px; color: #8a9690; }
header strong { font-size: 15px; }
.geometry-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 7px; margin: 12px 0; }
.geometry-grid > div { padding: 10px; background: #f3f7f4; border: 1px solid #e1e9e4; border-radius: 5px; }
.geometry-grid strong, .geometry-grid span { display: block; }
.geometry-grid strong { margin-top: 3px; font-size: 14px; }
.geometry-grid span { font-size: 8px; color: #8a9690; }
.geometry-grid .village { grid-column: 1 / -1; }
.source-card { position: relative; padding: 10px; margin: -4px 0 12px; background: #f7faf8; border: 1px solid #dfe8e3; border-radius: 5px; }
.source-card span { display: flex; flex-direction: column; }
.source-card strong { margin-top: 2px; font-size: 11px; color: #315f48; }
.source-card a { position: absolute; top: 10px; right: 10px; font-size: 9px; }
.source-card p { margin: 7px 0 0; font-size: 8px; color: #76827c; }
.attribute-form { padding-top: 12px; border-top: 1px solid #e6eae8; }
.attribute-form h3 { margin-bottom: 12px; font-size: 12px; }
.attribute-form label { display: grid; grid-template-columns: 78px minmax(0, 1fr); gap: 8px; align-items: center; margin-bottom: 10px; font-size: 10px; }
.attribute-form label > span b { color: #d4380d; }
.attribute-form :deep(.ant-select) { width: 100%; }
.status-row { display: flex; align-items: center; justify-content: space-between; padding: 9px 0; font-size: 10px; border-top: 1px dashed #e4e8e6; }
.actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 14px 0; }
.actions .ant-btn:last-child { grid-column: 1 / -1; }
.quality-card { padding: 12px; margin-top: 10px; background: #f7faf8; border: 1px solid #dfe8e3; border-radius: 6px; }
.quality-heading { display: flex; align-items: center; justify-content: space-between; }
.quality-heading > span { display: flex; flex-direction: column; }
.quality-heading strong { font-size: 24px; color: #2f6d4d; }
.quality-coverage { display: flex; justify-content: space-between; padding: 7px 0 2px; font-size: 9px; color: #66736c; }
.quality-card ul { padding: 0; margin: 10px 0 0; list-style: none; }
.quality-card li { padding: 8px 0; border-top: 1px dashed #dde5e0; }
.quality-card li > div { display: flex; align-items: center; justify-content: space-between; }
.quality-card li strong { font-size: 10px; }
.quality-card li p { margin: 4px 0 0; font-size: 9px; color: #76827c; }
.version-summary { padding: 9px; margin-top: 12px; font-size: 9px; color: #66736c; text-align: center; background: #f5f7f6; border-radius: 5px; }
</style>
