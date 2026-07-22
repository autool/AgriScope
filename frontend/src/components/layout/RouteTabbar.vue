<script setup lang="ts">
import {
  CloseOutlined,
  EllipsisOutlined,
  FullscreenExitOutlined,
  FullscreenOutlined,
  ReloadOutlined,
} from '@ant-design/icons-vue'
import { storeToRefs } from 'pinia'
import { watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useLayoutStore } from '@/store/layoutStore'
import { useTabbarStore } from '@/store/tabbarStore'

const route = useRoute()
const router = useRouter()
const layoutStore = useLayoutStore()
const tabbarStore = useTabbarStore()
const { tabsRef } = storeToRefs(tabbarStore)

watch(
  () => route.fullPath,
  () => tabbarStore.visitRoute(route),
  { immediate: true },
)

const activateTab = (path: string): void => {
  if (path !== route.fullPath) void router.push(path)
}

const closeTab = (path: string): void => {
  const nextPath = tabbarStore.closeTab(path)
  if (nextPath) void router.push(nextPath)
}

const closeOtherTabs = (): void => {
  tabbarStore.closeOtherTabs(route.fullPath)
}

const closeAllTabs = (): void => {
  void router.push(tabbarStore.closeAllTabs())
}
</script>

<template>
  <div class="route-tabbar">
    <div class="route-tabs" role="tablist" aria-label="已打开页面">
      <button
        v-for="tab in tabsRef"
        :key="tab.path"
        type="button"
        class="route-tab"
        :class="{ active: tab.path === route.fullPath }"
        role="tab"
        :aria-selected="tab.path === route.fullPath"
        @click="activateTab(tab.path)"
      >
        <i />
        <span>{{ tab.title }}</span>
        <CloseOutlined
          v-if="!tab.pinned"
          class="close-tab"
          @click.stop="closeTab(tab.path)"
        />
      </button>
    </div>
    <div class="tabbar-tools">
      <a-tooltip title="刷新当前页面状态">
        <button type="button" @click="layoutStore.refreshCurrentRoute()">
          <ReloadOutlined />
        </button>
      </a-tooltip>
      <a-tooltip :title="layoutStore.contentMaximizedRef ? '退出最大化' : '最大化内容区'">
        <button type="button" @click="layoutStore.toggleContentMaximized()">
          <FullscreenExitOutlined v-if="layoutStore.contentMaximizedRef" />
          <FullscreenOutlined v-else />
        </button>
      </a-tooltip>
      <a-dropdown placement="bottomRight">
        <button type="button"><EllipsisOutlined /></button>
        <template #overlay>
          <a-menu>
            <a-menu-item @click="closeOtherTabs">关闭其他标签</a-menu-item>
            <a-menu-item @click="closeAllTabs">关闭全部标签</a-menu-item>
          </a-menu>
        </template>
      </a-dropdown>
    </div>
  </div>
</template>

<style scoped lang="less">
.route-tabbar {
  display: flex;
  flex: 0 0 38px;
  min-width: 0;
  height: 38px;
  background: #f7f8f8;
  border-bottom: 1px solid #dfe4e1;
}

.route-tabs {
  display: flex;
  flex: 1;
  gap: 3px;
  min-width: 0;
  padding: 4px 6px 0;
  overflow-x: auto;
  scrollbar-width: thin;
}

.route-tab {
  display: flex;
  flex: 0 0 auto;
  gap: 6px;
  align-items: center;
  min-width: 104px;
  max-width: 180px;
  height: 33px;
  padding: 0 9px;
  font-size: 10px;
  color: #67736d;
  cursor: pointer;
  background: transparent;
  border: 1px solid transparent;
  border-bottom: 0;
  border-radius: 6px 6px 0 0;
}

.route-tab i {
  width: 5px;
  height: 5px;
  background: #aeb8b3;
  border-radius: 50%;
}

.route-tab span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.route-tab.active {
  color: #244d3a;
  background: #fff;
  border-color: #dfe4e1;
}

.route-tab.active i { background: #3e9a69; }
.close-tab { margin-left: auto; font-size: 9px; }

.tabbar-tools {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  padding: 0 5px;
  background: #fff;
  border-left: 1px solid #e1e5e3;
}

.tabbar-tools button {
  display: grid;
  width: 29px;
  height: 29px;
  color: #65726b;
  cursor: pointer;
  background: transparent;
  border: 0;
  border-radius: 5px;
  place-items: center;
}

.tabbar-tools button:hover { color: #286144; background: #edf4f0; }
</style>
