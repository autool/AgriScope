<script setup lang="ts">
import {
  AuditOutlined,
  BarChartOutlined,
  CloudUploadOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  DeploymentUnitOutlined,
  DiffOutlined,
  EditOutlined,
  EnvironmentOutlined,
  FileDoneOutlined,
  RadarChartOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import { storeToRefs } from 'pinia'
import { computed } from 'vue'

import { useLayoutStore } from '@/store/layoutStore'
import { useWorkbenchStore } from '@/store/workbenchStore'

const workbenchStore = useWorkbenchStore()
const layoutStore = useLayoutStore()
const { overviewRef } = storeToRefs(workbenchStore)

const navGroupsComputed = computed(() => [
  {
    label: '监测作业',
    items: [
      { path: '/dashboard', label: '项目总览', icon: DashboardOutlined },
      { path: '/production', label: '生产调度', icon: DeploymentUnitOutlined },
      { path: '/change-detection', label: '变化检测', icon: DiffOutlined },
      {
        path: '/imagery',
        label: '影像预处理',
        icon: CloudUploadOutlined,
        badge: overviewRef.value?.statistics.operational_imagery_count || undefined,
      },
      {
        path: '/interpretation',
        label: '地块解译',
        icon: EditOutlined,
        badge: overviewRef.value?.statistics.plot_count || undefined,
      },
      { path: '/statistics', label: '面积统计', icon: BarChartOutlined },
      {
        path: '/disaster',
        label: '灾害与长势',
        icon: RadarChartOutlined,
        badge: overviewRef.value?.statistics.pending_disaster_count || undefined,
      },
    ],
  },
  {
    label: '核查与交付',
    items: [
      {
        path: '/field',
        label: '内外业核查',
        icon: EnvironmentOutlined,
        badge: overviewRef.value?.statistics.pending_field_verification_count || undefined,
      },
      { path: '/review', label: '成果审核', icon: AuditOutlined },
      { path: '/delivery', label: '成果交付', icon: FileDoneOutlined },
    ],
  },
  {
    label: '资源管理',
    items: [
      { path: '/assets', label: '影像文件库', icon: DatabaseOutlined },
      { path: '/settings', label: '规则配置', icon: SettingOutlined },
    ],
  },
])

const remainingDaysComputed = computed<number>(() => {
  const deadline = overviewRef.value?.task.deadline
  if (!deadline) return 0
  const milliseconds = new Date(`${deadline}T23:59:59`).getTime() - Date.now()
  return Math.max(0, Math.ceil(milliseconds / 86_400_000))
})
</script>

<template>
  <nav
    class="module-sidebar"
    :class="{ collapsed: layoutStore.preferencesRef.sidebar.collapsed }"
  >
    <div v-for="group in navGroupsComputed" :key="group.label" class="nav-group">
      <div v-if="!layoutStore.preferencesRef.sidebar.collapsed" class="nav-group-label">
        {{ group.label }}
      </div>
      <a-tooltip
        v-for="item in group.items"
        :key="item.path"
        :title="layoutStore.preferencesRef.sidebar.collapsed ? item.label : undefined"
        placement="right"
      >
        <router-link :to="item.path" class="nav-item">
          <component :is="item.icon" />
          <span v-if="!layoutStore.preferencesRef.sidebar.collapsed">{{ item.label }}</span>
          <em v-if="item.badge && !layoutStore.preferencesRef.sidebar.collapsed">{{ item.badge }}</em>
          <i v-else-if="item.badge" class="badge-dot" />
        </router-link>
      </a-tooltip>
    </div>

    <div v-if="!layoutStore.preferencesRef.sidebar.collapsed" class="project-progress">
      <div class="progress-heading">
        <span>项目总体进度</span>
        <strong>{{ overviewRef?.project?.progress ?? 0 }}%</strong>
      </div>
      <a-progress
        :percent="overviewRef?.project?.progress ?? 0"
        :show-info="false"
        stroke-color="#4ca879"
        size="small"
      />
      <div class="progress-meta">
        <span>
          已解译 {{ overviewRef?.task.completed_plots || 0 }} /
          {{ overviewRef?.task.total_plots || 0 }} 地块
        </span>
        <span>剩余 {{ remainingDaysComputed }} 天</span>
      </div>
    </div>
  </nav>
</template>

<style scoped lang="less">
.module-sidebar {
  position: relative;
  padding: 14px 10px 128px;
  overflow: auto;
  color: #c6d0cb;
  background: #1a2d26;
  border-right: 1px solid #263c33;
}

.module-sidebar.collapsed { padding: 14px 8px; overflow-x: hidden; }
.module-sidebar.collapsed .nav-group + .nav-group { margin-top: 10px; }

.nav-group + .nav-group { margin-top: 16px; }
.nav-group-label { padding: 0 10px 6px; font-size: 9px; color: #73867d; letter-spacing: 1.2px; }

.nav-item {
  position: relative;
  display: grid;
  grid-template-columns: 20px 1fr auto;
  gap: 8px;
  align-items: center;
  height: 36px;
  padding: 0 10px;
  margin: 2px 0;
  font-size: 12px;
  color: #b8c5bf;
  text-decoration: none;
  border-radius: 6px;
}

.collapsed .nav-item {
  display: grid;
  grid-template-columns: 1fr;
  justify-items: center;
  width: 46px;
  height: 42px;
  padding: 0;
  margin: 3px auto;
}

.collapsed .nav-item.router-link-active { box-shadow: inset 2px 0 #79c79c; }

.nav-item:hover { color: #fff; background: rgb(255 255 255 / 5%); }
.nav-item.router-link-active { color: #fff; background: #2d644c; box-shadow: inset 3px 0 #79c79c; }
.nav-item > :first-child { font-size: 15px; }
.nav-item em { min-width: 20px; padding: 1px 5px; font-size: 9px; font-style: normal; text-align: center; background: rgb(255 255 255 / 10%); border-radius: 10px; }
.badge-dot { position: absolute; top: 8px; right: 8px; width: 5px; height: 5px; background: #f2bc58; border-radius: 50%; }

.project-progress {
  position: absolute;
  right: 12px;
  bottom: 16px;
  left: 12px;
  padding: 12px;
  background: rgb(255 255 255 / 4%);
  border: 1px solid rgb(255 255 255 / 7%);
  border-radius: 7px;
}

.progress-heading,
.progress-meta { display: flex; justify-content: space-between; }
.progress-heading { margin-bottom: 6px; font-size: 10px; }
.progress-heading strong { color: #8dd1a9; }
.progress-meta { margin-top: 5px; font-size: 8px; color: #71867c; }
</style>
