<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import GrowthMonitoringPanel from '@/components/growth/GrowthMonitoringPanel.vue'
import DisasterPanel from '@/components/panels/DisasterPanel.vue'
import { useLayerStore } from '@/store/layerStore'

const layerStore = useLayerStore()
const route = useRoute()
const activeTabRef = ref<'disaster' | 'growth'>(
  route.query.monitor === 'growth' ? 'growth' : 'disaster',
)

watch(
  activeTabRef,
  (tab) => {
    layerStore.setVisibility('disaster', tab === 'disaster')
    layerStore.setVisibility('growth', tab === 'growth')
  },
  { immediate: true },
)
</script>

<template>
  <a-tabs v-model:active-key="activeTabRef" class="monitoring-tabs" destroy-inactive-tab-pane>
    <a-tab-pane key="disaster" tab="灾害斑块"><DisasterPanel /></a-tab-pane>
    <a-tab-pane key="growth" tab="作物长势"><GrowthMonitoringPanel /></a-tab-pane>
  </a-tabs>
</template>

<style scoped>
.monitoring-tabs { height: 100%; }
:deep(.ant-tabs-nav) { margin: 0; padding: 0 12px; }
:deep(.ant-tabs-content-holder), :deep(.ant-tabs-content), :deep(.ant-tabs-tabpane) { height: 100%; min-height: 0; }
</style>
