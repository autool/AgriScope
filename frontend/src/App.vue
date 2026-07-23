<script setup lang="ts">
import {
  BellOutlined,
  CloudServerOutlined,
  RadarChartOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import { storeToRefs } from 'pinia'
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import UserIdentitySwitcher from '@/components/layout/UserIdentitySwitcher.vue'
import { useLayoutStore } from '@/store/layoutStore'
import { useSystemHealthStore } from '@/store/systemHealthStore'
import { useWorkbenchStore } from '@/store/workbenchStore'

interface TaskNotification {
  key: string
  title: string
  description: string
  count: number
  route: string
  severity: 'warning' | 'error' | 'info'
}

const layoutStore = useLayoutStore()
const systemHealthStore = useSystemHealthStore()
const workbenchStore = useWorkbenchStore()
const router = useRouter()
const route = useRoute()
const { loadingRef, overviewRef } = storeToRefs(workbenchStore)
const standaloneComputed = computed<boolean>(() => route.meta.standalone === true)

const projectNameComputed = computed<string>(() => (
  overviewRef.value?.project.project_name || '加载项目上下文'
))
const serviceStateComputed = computed<{ label: string; state: string }>(() => {
  if (systemHealthStore.stateRef === 'checking' || loadingRef.value) {
    return { label: '平台与数据库检查中', state: 'loading' }
  }
  if (systemHealthStore.stateRef === 'online') {
    return { label: '平台与数据库可用', state: 'online' }
  }
  return { label: '平台或数据库离线', state: 'offline' }
})

onMounted(() => systemHealthStore.start())
onUnmounted(() => systemHealthStore.stop())
const notificationsComputed = computed<TaskNotification[]>(() => {
  const overview = overviewRef.value
  if (!overview) return []
  const notifications: TaskNotification[] = []
  const imageryStage = overview.workflow.stages.find(
    (stage) => stage.code === 'imagery',
  )
  const deliveryStage = overview.workflow.stages.find(
    (stage) => stage.code === 'delivery',
  )
  if (imageryStage?.status === 'blocked') {
    notifications.push({
      key: 'imagery-blocked',
      title: '业务影像缺失',
      description: imageryStage.detail,
      count: 1,
      route: '/assets',
      severity: 'error',
    })
  }
  if (overview.statistics.open_issue_count > 0) {
    notifications.push({
      key: 'quality-issues',
      title: '质量问题待整改',
      description: `${overview.statistics.open_issue_count} 条问题仍未关闭`,
      count: overview.statistics.open_issue_count,
      route: '/interpretation',
      severity: 'warning',
    })
  }
  if (overview.statistics.pending_field_verification_count > 0) {
    notifications.push({
      key: 'field-pending',
      title: '外业疑点待处置',
      description: `${overview.statistics.pending_field_verification_count} 条外业记录尚未闭环`,
      count: overview.statistics.pending_field_verification_count,
      route: '/field',
      severity: 'warning',
    })
  }
  if (overview.statistics.pending_disaster_count > 0) {
    notifications.push({
      key: 'disaster-pending',
      title: '灾害斑块待复核',
      description: `${overview.statistics.pending_disaster_count} 个灾害斑块等待人工确认`,
      count: overview.statistics.pending_disaster_count,
      route: '/disaster',
      severity: 'warning',
    })
  }
  if (overview.task.status === 'rejected') {
    notifications.push({
      key: 'task-rejected',
      title: '审核任务已驳回',
      description: '请进入成果审核查看最近审核意见并组织整改',
      count: 1,
      route: '/review',
      severity: 'error',
    })
  }
  if (deliveryStage?.status === 'active') {
    notifications.push({
      key: 'delivery-ready',
      title: '成果包等待生成',
      description: '三级审核已完成，可由项目负责人生成成果包',
      count: 1,
      route: '/delivery',
      severity: 'info',
    })
  }
  return notifications
})
const notificationCountComputed = computed<number>(() => (
  notificationsComputed.value.reduce((total, item) => total + item.count, 0)
))

const navigateNotification = (item: TaskNotification): void => {
  void router.push(item.route)
}
</script>

<template>
  <router-view v-if="standaloneComputed" />
  <a-layout v-else class="application-shell">
    <a-layout-header v-if="!layoutStore.contentMaximizedRef" class="application-header">
      <div class="brand-lockup">
        <div class="brand-mark"><RadarChartOutlined /></div>
        <div class="brand-copy">
          <h1>遥感监测内业处理与成果审核平台</h1>
          <p>REMOTE SENSING MONITORING WORKSPACE</p>
        </div>
      </div>

      <div class="header-separator" />
      <a-tooltip title="当前工作区仅配置一个监测项目">
        <div class="project-context">
          <span class="project-icon"><CloudServerOutlined /></span>
          <span>
            <small>当前项目</small>
            <strong>{{ projectNameComputed }}</strong>
          </span>
        </div>
      </a-tooltip>

      <div class="header-actions">
        <div class="online-state" :class="serviceStateComputed.state">
          <i /> {{ serviceStateComputed.label }}
        </div>
        <a-dropdown :trigger="['click']" placement="bottomRight">
          <a-badge
            :count="notificationCountComputed"
            :overflow-count="99"
            size="small"
          >
            <a-button class="header-icon-button" type="text" aria-label="任务通知">
              <BellOutlined />
            </a-button>
          </a-badge>
          <template #overlay>
            <a-menu class="notification-menu">
              <a-menu-item
                v-for="item in notificationsComputed"
                :key="item.key"
                @click="navigateNotification(item)"
              >
                <div class="notification-item">
                  <i :class="item.severity" />
                  <span>
                    <strong>{{ item.title }}</strong>
                    <small>{{ item.description }}</small>
                  </span>
                  <a-tag>{{ item.count }}</a-tag>
                </div>
              </a-menu-item>
              <a-menu-item v-if="notificationsComputed.length === 0" disabled>
                <div class="notification-empty">当前任务没有待办通知</div>
              </a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
        <a-tooltip title="界面与布局设置">
          <a-button
            class="header-icon-button"
            type="text"
            aria-label="界面与布局设置"
            @click="layoutStore.openPreferences()"
          >
            <SettingOutlined />
          </a-button>
        </a-tooltip>
        <UserIdentitySwitcher />
      </div>
    </a-layout-header>

    <a-layout-content
      class="application-content"
      :class="{ maximized: layoutStore.contentMaximizedRef }"
    >
      <router-view />
    </a-layout-content>
  </a-layout>
</template>

<style scoped lang="less">
.application-shell {
  min-height: 100vh;
  background: #f3f5f7;
}

.application-header {
  z-index: 30;
  display: flex;
  align-items: center;
  height: 58px;
  padding: 0 18px;
  line-height: normal;
  color: #fff;
  background: #14251f;
  border-bottom: 1px solid rgb(255 255 255 / 8%);
  box-shadow: 0 2px 10px rgb(12 29 23 / 16%);
}

.brand-lockup,
.project-context,
.header-actions,
.online-state {
  display: flex;
  align-items: center;
}

.brand-mark {
  display: grid;
  width: 36px;
  height: 36px;
  margin-right: 10px;
  font-size: 19px;
  color: #f0c35b;
  background: rgb(255 255 255 / 8%);
  border: 1px solid rgb(255 255 255 / 13%);
  border-radius: 8px;
  place-items: center;
}

.brand-copy {
  display: flex;
  flex-direction: column;
  gap: 1px;
  justify-content: center;
}

.brand-copy h1 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  line-height: 22px;
  letter-spacing: 0.5px;
}

.brand-copy p {
  margin: 0;
  font-size: 8px;
  line-height: 11px;
  color: rgb(255 255 255 / 43%);
  letter-spacing: 1.45px;
}

.header-separator {
  width: 1px;
  height: 28px;
  margin: 0 18px;
  background: rgb(255 255 255 / 11%);
}

.project-context {
  gap: 9px;
  padding: 5px 8px;
  color: #fff;
  border-radius: 6px;
}

.project-icon {
  font-size: 17px;
  color: #8bc9a8;
}

.project-context > span:nth-child(2) {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.project-context small {
  font-size: 9px;
  line-height: 12px;
  color: rgb(255 255 255 / 46%);
}

.project-context strong {
  font-size: 12px;
  font-weight: 500;
  line-height: 17px;
}

.header-actions {
  gap: 16px;
  margin-left: auto;
}

.online-state {
  gap: 7px;
  font-size: 11px;
  color: #b7c8bf;
}

.online-state i {
  width: 6px;
  height: 6px;
  background: #5bcd85;
  border-radius: 50%;
  box-shadow: 0 0 0 3px rgb(91 205 133 / 12%);
}

.online-state.loading i { background: #e4ae4f; }
.online-state.offline i { background: #d85d54; }

.header-icon-button {
  color: #c8d4ce;
}

.header-icon-button:hover {
  color: #fff !important;
  background: rgb(255 255 255 / 7%) !important;
}

.application-content {
  min-height: calc(100vh - 58px);
}

.application-content.maximized { min-height: 100vh; }

.notification-menu { width: 330px; }
.notification-item { display: grid; grid-template-columns: 8px minmax(0, 1fr) auto; gap: 9px; align-items: start; padding: 3px 0; }
.notification-item > i { width: 7px; height: 7px; margin-top: 5px; background: #4b8fc8; border-radius: 50%; }
.notification-item > i.warning { background: #d99a3b; }
.notification-item > i.error { background: #d65a50; }
.notification-item > span { display: flex; min-width: 0; flex-direction: column; }
.notification-item strong { font-size: 11px; color: #263a30; }
.notification-item small { overflow: hidden; font-size: 9px; color: #809087; text-overflow: ellipsis; white-space: nowrap; }
.notification-empty { padding: 8px 4px; font-size: 10px; color: #8a9690; text-align: center; }
</style>
