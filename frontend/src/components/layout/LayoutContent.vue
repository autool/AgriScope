<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { useLayoutStore } from '@/store/layoutStore'

const route = useRoute()
const layoutStore = useLayoutStore()

const routeKeyComputed = computed<string>(() => (
  `${route.fullPath}:${layoutStore.routeRefreshKeyRef}`
))
const boxedComputed = computed<boolean>(() => (
  layoutStore.preferencesRef.app.contentMode === 'boxed'
  && route.meta.fullWidth !== true
))
const keepAliveComputed = computed<boolean>(() => (
  layoutStore.preferencesRef.tabbar.keepAlive
  && route.meta.keepAlive !== false
))
</script>

<template>
  <main
    class="layout-content"
    :class="{
      'layout-content-boxed': boxedComputed,
      'layout-content-compact': layoutStore.preferencesRef.app.density === 'compact',
    }"
  >
    <router-view v-slot="{ Component }">
      <transition
        v-if="layoutStore.preferencesRef.transition.enabled"
        name="workspace-fade-slide"
        mode="out-in"
      >
        <keep-alive v-if="keepAliveComputed" :max="12">
          <component :is="Component" :key="routeKeyComputed" />
        </keep-alive>
        <component :is="Component" v-else :key="routeKeyComputed" />
      </transition>
      <template v-else>
        <keep-alive v-if="keepAliveComputed" :max="12">
          <component :is="Component" :key="routeKeyComputed" />
        </keep-alive>
        <component :is="Component" v-else :key="routeKeyComputed" />
      </template>
    </router-view>
  </main>
</template>

<style scoped lang="less">
.layout-content {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.layout-content-boxed {
  width: min(1440px, calc(100% - 32px));
  margin: 12px auto;
  overflow: auto;
  background: #fff;
  border: 1px solid #dde3e0;
  border-radius: 8px;
}

.layout-content-compact :deep(.panel),
.layout-content-compact :deep(.page-section) {
  padding: 10px;
}

.workspace-fade-slide-enter-active,
.workspace-fade-slide-leave-active {
  transition: opacity 130ms ease, transform 130ms ease;
}

.workspace-fade-slide-enter-from {
  opacity: 0;
  transform: translateX(5px);
}

.workspace-fade-slide-leave-to {
  opacity: 0;
  transform: translateX(-3px);
}
</style>
