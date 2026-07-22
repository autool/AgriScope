<script setup lang="ts">
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { onMounted } from 'vue'

import ThematicMapGenerationPanel from '@/components/thematic-map/ThematicMapGenerationPanel.vue'
import ThematicMapProductGrid from '@/components/thematic-map/ThematicMapProductGrid.vue'
import ThematicMapTemplatePanel from '@/components/thematic-map/ThematicMapTemplatePanel.vue'
import { useThematicMapStore } from '@/store/thematicMapStore'
import type {
  ThematicMapBatchGeneratePayload,
  ThematicMapTemplateCreatePayload,
} from '@/types/thematicMap'

const thematicMapStore = useThematicMapStore()
const {
  canGenerateComputed,
  canManageComputed,
  generatingRef,
  loadingRef,
  overviewRef,
  savingTemplateRef,
} = storeToRefs(thematicMapStore)

const handleCreateTemplate = async (
  payload: Omit<ThematicMapTemplateCreatePayload, 'operator_code'>,
): Promise<void> => {
  try {
    await thematicMapStore.createTemplate(payload)
    message.success('专题图版式模板已保存并记录审计')
  } catch {
    // 请求层已提供安全错误提示。
  }
}

const handleGenerate = async (
  payload: Omit<ThematicMapBatchGeneratePayload, 'operator_code'>,
): Promise<void> => {
  try {
    const count = await thematicMapStore.generate(payload)
    message.success(`已生成并校验 ${count} 张专题图实体成果`)
  } catch {
    // 请求层已提供安全错误提示。
  }
}

onMounted(() => {
  void thematicMapStore.load()
})
</script>

<template>
  <div class="thematic-map-view">
    <section class="summary-strip">
      <span><small>LAYOUT TEMPLATES</small><strong>{{ overviewRef?.template_count || 0 }}</strong><em>持久化版式</em></span>
      <span><small>VERIFIED SOURCES</small><strong>{{ overviewRef?.eligible_source_count || 0 }}</strong><em>可用实体影像</em></span>
      <span><small>MAP PRODUCTS</small><strong>{{ overviewRef?.product_count || 0 }}</strong><em>校验专题图</em></span>
      <a-alert
        v-if="!canGenerateComputed"
        type="info"
        show-icon
        message="当前身份可查看专题图，批量生成仅限项目负责人。"
      />
    </section>
    <a-spin :spinning="loadingRef" class="workspace-spin">
      <section class="composer-grid">
        <ThematicMapTemplatePanel
          :templates="overviewRef?.templates || []"
          :disabled="!canManageComputed"
          :loading="savingTemplateRef"
          @create="handleCreateTemplate"
        />
        <ThematicMapGenerationPanel
          :templates="overviewRef?.templates || []"
          :sources="overviewRef?.sources || []"
          :disabled="!canGenerateComputed || !(overviewRef?.templates.length)"
          :loading="generatingRef"
          @generate="handleGenerate"
        />
      </section>
      <ThematicMapProductGrid :products="overviewRef?.products || []" />
    </a-spin>
  </div>
</template>

<style scoped>
.thematic-map-view { display: grid; grid-template-rows: auto minmax(0, 1fr); gap: 10px; height: 100%; padding: 10px; background: #eef2f0; }
.summary-strip { display: grid; grid-template-columns: repeat(3, minmax(140px, 190px)) minmax(260px, 1fr); gap: 8px; }
.summary-strip > span { display: flex; flex-direction: column; padding: 10px 12px; background: #fff; border: 1px solid #dfe5e2; border-radius: 7px; }
.summary-strip small { font-size: 7px; color: #8b9791; }
.summary-strip strong { font-size: 20px; color: #347958; }
.summary-strip em { font-size: 8px; font-style: normal; color: #77867e; }
.workspace-spin { min-height: 0; }
.workspace-spin :deep(.ant-spin-container) { display: grid; grid-template-rows: minmax(390px, 0.8fr) minmax(250px, 1fr); gap: 10px; height: 100%; min-height: 0; }
.composer-grid { display: grid; grid-template-columns: minmax(420px, 1fr) minmax(420px, 1fr); gap: 10px; min-height: 0; }
@media (max-width: 1180px) {
  .summary-strip { grid-template-columns: repeat(3, 1fr); }
  .summary-strip :deep(.ant-alert) { grid-column: 1 / -1; }
  .composer-grid { grid-template-columns: 1fr; overflow: auto; }
}
</style>
