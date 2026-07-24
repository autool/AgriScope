<script setup lang="ts">
import { computed } from 'vue'

import PlotAttributeFieldManager from '@/components/settings/PlotAttributeFieldManager.vue'
import { useWorkbenchStore } from '@/store/workbenchStore'

const workbenchStore = useWorkbenchStore()
const projectCodeComputed = computed<string>(() => workbenchStore.projectCodeComputed)
</script>

<template>
  <div class="settings-fields-view">
    <a-alert
      type="info"
      show-icon
      message="地块字段模式独立维护"
      description="字段定义会同步用于编辑、批量回写、质量检查、矢量成果和最终交付；修改后旧工作簿不会被静默兼容。"
    />
    <PlotAttributeFieldManager :project-code="projectCodeComputed" />
  </div>
</template>

<style scoped>
.settings-fields-view { width: min(1040px, 100%); margin: 0 auto; }
</style>
