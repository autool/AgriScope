<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'

import MobileUavCaptureForm from '@/components/uav/mobile/MobileUavCaptureForm.vue'
import { useUavCaptureStore } from '@/store/uavCaptureStore'
import { useUserStore } from '@/store/userStore'

const route = useRoute()
const captureStore = useUavCaptureStore()
const userStore = useUserStore()

onMounted(async () => {
  document.documentElement.classList.add('mobile-standalone')
  const projectCode = typeof route.query.project_code === 'string'
    ? route.query.project_code
    : 'RS-2026'
  captureStore.setProjectCode(projectCode)
  captureStore.startNetworkMonitoring()
  await userStore.initialize(projectCode)
  if (!userStore.hasCapability('operate_uav_missions')) {
    const operator = userStore.usersRef.find(
      (user) => user.capabilities.includes('operate_uav_missions'),
    )
    if (operator) userStore.setCurrentUser(operator.user_code)
  }
  try {
    await captureStore.load()
  } catch {
    // 请求层和移动表单会显示安全错误状态。
  }
})

onUnmounted(() => {
  captureStore.stopNetworkMonitoring()
  document.documentElement.classList.remove('mobile-standalone')
})
</script>

<template>
  <div class="uav-capture-view">
    <MobileUavCaptureForm />
  </div>
</template>

<style scoped>
.uav-capture-view { min-height: 100vh; padding: 14px 0 36px; background: #edf2f0; }
</style>
