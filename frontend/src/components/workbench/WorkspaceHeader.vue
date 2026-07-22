<script setup lang="ts">
import {
  FolderOpenOutlined,
  HistoryOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import { storeToRefs } from 'pinia'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useLayoutStore } from '@/store/layoutStore'
import { useWorkbenchStore } from '@/store/workbenchStore'

const route = useRoute()
const router = useRouter()
const workbenchStore = useWorkbenchStore()
const layoutStore = useLayoutStore()
const { overviewRef } = storeToRefs(workbenchStore)

const statusLabels: Record<string, string> = {
  interpreting: '解译中',
  self_check: '内业自检',
  quality_review: '质检审核',
  client_review: '甲方复核',
  completed: '审核完成',
  rejected: '已驳回',
}
const statusLabelComputed = computed(() => (
  statusLabels[overviewRef.value?.task.status || ''] || '进行中'
))
</script>

<template>
  <header class="workspace-header">
    <a-tooltip :title="layoutStore.preferencesRef.sidebar.collapsed ? '展开侧栏' : '折叠侧栏'">
      <button class="sidebar-toggle" type="button" @click="layoutStore.toggleSidebar()">
        <MenuUnfoldOutlined v-if="layoutStore.preferencesRef.sidebar.collapsed" />
        <MenuFoldOutlined v-else />
      </button>
    </a-tooltip>
    <div class="workspace-heading">
      <div class="workspace-eyebrow">监测作业 / {{ route.meta.title }}</div>
      <div class="workspace-title-row">
        <h2>{{ route.meta.title }}</h2>
        <a-tag :color="overviewRef?.task?.status === 'completed' ? 'green' : 'processing'">
          {{ statusLabelComputed }}
        </a-tag>
        <span>{{ overviewRef?.task?.task_code }} · {{ route.meta.description }}</span>
      </div>
    </div>
    <div class="workspace-actions">
      <a-button @click="router.push('/review')"><HistoryOutlined /> 审核记录</a-button>
      <a-button @click="router.push('/delivery')"><FolderOpenOutlined /> 成果交付</a-button>
      <a-tooltip title="界面与布局设置">
        <a-button aria-label="界面与布局设置" @click="layoutStore.openPreferences()">
          <SettingOutlined />
        </a-button>
      </a-tooltip>
    </div>
  </header>
</template>

<style scoped>
.workspace-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px 0 18px;
  background: #fff;
  border-bottom: 1px solid #dfe4e1;
  flex: 0 0 62px;
}

.sidebar-toggle {
  display: grid;
  flex: 0 0 32px;
  width: 32px;
  height: 32px;
  margin-right: 10px;
  color: #5d6c64;
  cursor: pointer;
  background: #f6f8f7;
  border: 1px solid #e0e5e2;
  border-radius: 5px;
  place-items: center;
}

.sidebar-toggle:hover { color: #286044; background: #edf4f0; }
.workspace-heading { min-width: 0; }

.workspace-eyebrow { margin-bottom: 3px; font-size: 9px; color: #8a9690; }
.workspace-title-row { display: flex; gap: 8px; align-items: center; }
.workspace-title-row h2 { margin: 0; font-size: 17px; line-height: 22px; }
.workspace-title-row > span:last-child { font-size: 11px; color: #6e7b75; }
.workspace-actions { display: flex; gap: 8px; }
</style>
