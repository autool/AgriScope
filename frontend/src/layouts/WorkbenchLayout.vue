<script setup lang="ts">
import { computed, onMounted } from 'vue'

import LayoutContent from '@/components/layout/LayoutContent.vue'
import LayoutPreferencesDrawer from '@/components/layout/LayoutPreferencesDrawer.vue'
import RouteTabbar from '@/components/layout/RouteTabbar.vue'
import ModuleSidebar from '@/components/workbench/ModuleSidebar.vue'
import WorkspaceHeader from '@/components/workbench/WorkspaceHeader.vue'
import { useLayoutStore } from '@/store/layoutStore'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'

const workbenchStore = useWorkbenchStore()
const layoutStore = useLayoutStore()
const userStore = useUserStore()

const layoutStyleComputed = computed<Record<string, string>>(() => ({
  '--sidebar-width': `${layoutStore.sidebarWidthComputed}px`,
}))

onMounted(() => {
  void Promise.all([
    userStore.initialize(),
    workbenchStore.initialize(),
  ])
})
</script>

<template>
  <div
    class="workbench-layout"
    :class="{ 'content-maximized': layoutStore.contentMaximizedRef }"
    :style="layoutStyleComputed"
  >
    <ModuleSidebar v-if="!layoutStore.contentMaximizedRef" />
    <section class="workspace-shell">
      <WorkspaceHeader
        v-if="layoutStore.preferencesRef.header.workspaceVisible && !layoutStore.contentMaximizedRef"
      />
      <RouteTabbar v-if="layoutStore.preferencesRef.tabbar.enabled" />
      <LayoutContent />
      <footer v-if="!layoutStore.contentMaximizedRef" class="workspace-footer">
        <span>数据坐标系：CGCS2000 / EPSG:4490</span>
        <span>服务版本 v1.0.0</span>
      </footer>
    </section>
    <LayoutPreferencesDrawer />
  </div>
</template>

<style scoped>
.workbench-layout {
  display: grid;
  grid-template-columns: var(--sidebar-width) minmax(0, 1fr);
  height: calc(100vh - 58px);
  color: #26332d;
  background: #eef1f3;
  transition: grid-template-columns 160ms ease;
}

.workbench-layout.content-maximized { grid-template-columns: minmax(0, 1fr); height: 100vh; }
.workspace-shell {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.workspace-footer { display: flex; align-items: center; justify-content: space-between; padding: 0 14px; font-size: 8px; color: #74817b; background: #f8f9f9; border-top: 1px solid #dfe4e1; }
.workspace-footer { flex: 0 0 28px; }
</style>
