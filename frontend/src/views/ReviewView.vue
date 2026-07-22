<script setup lang="ts">
import ReviewPanel from '@/components/panels/ReviewPanel.vue'
import SpatialWorkbench from '@/components/workbench/SpatialWorkbench.vue'
</script>

<template>
  <SpatialWorkbench>
    <template #spatial-toolbar><div class="review-toolbar"><strong>成果审核定位图</strong><span>支持问题图斑定位、版本对比和边界复核</span></div></template>
    <template #panel><ReviewPanel /></template>
  </SpatialWorkbench>
</template>

<style scoped>
.review-toolbar { display: flex; gap: 10px; align-items: center; font-size: 8px; }
.review-toolbar strong { font-size: 10px; }
</style>
