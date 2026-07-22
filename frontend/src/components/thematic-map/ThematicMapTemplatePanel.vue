<script setup lang="ts">
import { message } from 'ant-design-vue'
import { reactive } from 'vue'

import type {
  ThematicMapTemplate,
  ThematicMapTemplateCreatePayload,
} from '@/types/thematicMap'

defineProps<{
  templates: ThematicMapTemplate[]
  disabled: boolean
  loading: boolean
}>()

const emit = defineEmits<{
  create: [payload: Omit<ThematicMapTemplateCreatePayload, 'operator_code'>]
}>()

const form = reactive({
  templateCode: 'HLJ-AGRI-LANDSCAPE',
  templateName: '农业遥感专题图横版',
  titlePattern: '{map_name}',
  producer: '',
  pageWidthPx: 1800,
  pageHeightPx: 1200,
  dpi: 150,
  marginPx: 60,
  legendPosition: 'bottom_right' as 'bottom_right' | 'bottom_left',
  includeNeatline: true,
  includeNorthArrow: true,
  includeScaleBar: true,
  comment: '建立项目专题图标准版式模板',
})

const submit = (): void => {
  if (!form.templateCode.trim() || !form.templateName.trim()) {
    message.warning('请填写模板编号和名称')
    return
  }
  if (!form.producer.trim()) {
    message.warning('请填写真实制图单位')
    return
  }
  emit('create', {
    template_code: form.templateCode.trim(),
    template_name: form.templateName.trim(),
    title_pattern: form.titlePattern.trim(),
    producer: form.producer.trim(),
    page_width_px: form.pageWidthPx,
    page_height_px: form.pageHeightPx,
    dpi: form.dpi,
    margin_px: form.marginPx,
    legend_position: form.legendPosition,
    include_neatline: form.includeNeatline,
    include_north_arrow: form.includeNorthArrow,
    include_scale_bar: form.includeScaleBar,
    comment: form.comment.trim(),
  })
}
</script>

<template>
  <section class="template-panel">
    <header>
      <span><small>LAYOUT TEMPLATES</small><strong>专题图版式模板</strong></span>
      <a-tag>{{ templates.length }} 套</a-tag>
    </header>
    <div v-if="templates.length" class="template-list">
      <article v-for="template in templates" :key="template.template_code">
        <strong>{{ template.template_name }}</strong>
        <small>{{ template.template_code }} · {{ template.page_width_px }}×{{ template.page_height_px }} · {{ template.dpi }} DPI</small>
        <span>{{ template.producer }}</span>
      </article>
    </div>
    <a-empty v-else description="尚未创建真实版式模板" />
    <a-divider>新建模板</a-divider>
    <div class="template-form">
      <label><span>模板编号</span><a-input v-model:value="form.templateCode" /></label>
      <label><span>模板名称</span><a-input v-model:value="form.templateName" /></label>
      <label><span>标题模式</span><a-input v-model:value="form.titlePattern" /></label>
      <label><span>制图单位</span><a-input v-model:value="form.producer" placeholder="填写实际制图单位" /></label>
      <label><span>图幅宽度</span><a-input-number v-model:value="form.pageWidthPx" :min="800" :max="8000" /></label>
      <label><span>图幅高度</span><a-input-number v-model:value="form.pageHeightPx" :min="600" :max="8000" /></label>
      <label><span>输出 DPI</span><a-input-number v-model:value="form.dpi" :min="72" :max="600" /></label>
      <label><span>页边距</span><a-input-number v-model:value="form.marginPx" :min="20" :max="800" /></label>
      <label><span>图例位置</span><a-select v-model:value="form.legendPosition" :options="[{ value: 'bottom_right', label: '右下' }, { value: 'bottom_left', label: '左下' }]" /></label>
      <div class="switches">
        <a-checkbox v-model:checked="form.includeNeatline">图廓</a-checkbox>
        <a-checkbox v-model:checked="form.includeNorthArrow">指北针</a-checkbox>
        <a-checkbox v-model:checked="form.includeScaleBar">比例尺</a-checkbox>
      </div>
      <label class="wide"><span>创建说明</span><a-textarea v-model:value="form.comment" :rows="2" /></label>
    </div>
    <a-button
      type="primary"
      block
      :disabled="disabled"
      :loading="loading"
      @click="submit"
    >
      保存版式模板
    </a-button>
  </section>
</template>

<style scoped>
.template-panel { height: 100%; padding: 14px; overflow: auto; background: #fff; border: 1px solid #dfe5e2; border-radius: 8px; }
header { display: flex; align-items: center; justify-content: space-between; }
header span { display: flex; flex-direction: column; }
header small { font-size: 8px; color: #87948d; }
header strong { font-size: 13px; }
.template-list { display: grid; gap: 7px; margin-top: 12px; }
.template-list article { display: flex; flex-direction: column; gap: 2px; padding: 9px; background: #f5f8f6; border: 1px solid #e4e9e6; border-radius: 6px; }
.template-list strong { font-size: 10px; }
.template-list small, .template-list span { font-size: 8px; color: #78867f; }
.template-form { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px; }
.template-form label { display: grid; gap: 4px; font-size: 8px; color: #6f7e76; }
.template-form :deep(.ant-input-number), .template-form :deep(.ant-select) { width: 100%; }
.wide, .switches { grid-column: 1 / -1; }
.switches { display: flex; gap: 12px; padding: 6px 0; }
</style>
