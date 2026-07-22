<script setup lang="ts">
import InterpretationPanel from '@/components/panels/InterpretationPanel.vue'
import SpatialWorkbench from '@/components/workbench/SpatialWorkbench.vue'
</script>

<template>
  <SpatialWorkbench editing>
    <template #panel><InterpretationPanel /></template>
  </SpatialWorkbench>
</template>
