<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'

import MobileFieldCaptureForm from '@/components/field/mobile/MobileFieldCaptureForm.vue'
import { useFieldCaptureStore } from '@/store/fieldCaptureStore'
import { useUserStore } from '@/store/userStore'

const route = useRoute()
const captureStore = useFieldCaptureStore()
const userStore = useUserStore()

onMounted(async () => {
  document.documentElement.classList.add('mobile-standalone')
  const projectCode = typeof route.query.project_code === 'string'
    ? route.query.project_code
    : 'RS-2026'
  const taskCode = typeof route.query.task_code === 'string'
    ? route.query.task_code
    : 'RS-2026-045'
  captureStore.setTaskCode(taskCode)
  captureStore.startNetworkMonitoring()
  await userStore.initialize(projectCode)
  if (!userStore.hasCapability('upload_field_data')) {
    const fieldUser = userStore.usersRef.find(
      (user) => user.capabilities.includes('upload_field_data'),
    )
    if (fieldUser) userStore.setCurrentUser(fieldUser.user_code)
  }
})

onUnmounted(() => {
  captureStore.stopNetworkMonitoring()
  document.documentElement.classList.remove('mobile-standalone')
})
</script>

<template>
  <div class="field-capture-view">
    <MobileFieldCaptureForm />
  </div>
</template>

<style scoped>
.field-capture-view { min-height: 100vh; padding: 14px 0 36px; background: #eef3f0; }
</style>
