<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { onMounted } from 'vue'

import FieldVerificationPanel from '@/components/panels/FieldVerificationPanel.vue'
import SpatialWorkbench from '@/components/workbench/SpatialWorkbench.vue'
import { useRuleConfigStore } from '@/store/ruleConfigStore'

const ruleConfigStore = useRuleConfigStore()
const { configRef } = storeToRefs(ruleConfigStore)

onMounted(() => {
  if (!configRef.value) void ruleConfigStore.load()
})
</script>

<template>
  <SpatialWorkbench>
    <template #spatial-toolbar>
      <div class="field-toolbar">
        <strong>点斑空间匹配</strong>
        <span>偏差阈值：{{ configRef?.field_offset_threshold_m ?? '--' }} m</span>
        <span>搜索半径：{{ configRef?.field_search_radius_m ?? '--' }} m</span>
        <span>时间差：{{ configRef?.max_capture_image_days ?? '--' }} 天</span>
        <a-tag color="orange">异常点优先</a-tag>
      </div>
    </template>
    <template #panel><FieldVerificationPanel /></template>
  </SpatialWorkbench>
</template>

<style scoped>
.field-toolbar { display: flex; gap: 12px; align-items: center; font-size: 8px; }
.field-toolbar strong { font-size: 10px; }
</style>
