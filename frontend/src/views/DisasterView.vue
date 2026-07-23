<script setup lang="ts">
import DisasterGrowthPanel from '@/components/panels/DisasterGrowthPanel.vue'
import SpatialWorkbench from '@/components/workbench/SpatialWorkbench.vue'
</script>

<template>
  <SpatialWorkbench>
    <template #spatial-toolbar><div class="legend"><strong>灾害与长势专题</strong><span><i class="light" />轻度</span><span><i class="medium" />中度</span><span><i class="heavy" />重度/转差</span><span><i class="good" />长势转好</span></div></template>
    <template #panel><DisasterGrowthPanel /></template>
  </SpatialWorkbench>
</template>

<style scoped>
.legend { display: flex; gap: 12px; align-items: center; font-size: 8px; }
.legend strong { font-size: 10px; }
.legend span { display: flex; gap: 4px; align-items: center; }
.legend i { width: 8px; height: 8px; background: #f0b24b; border-radius: 2px; }
.legend i.medium { background: #ef7f36; }
.legend i.heavy { background: #dc4c3f; }
.legend i.good { background: #3e975b; }
</style>
