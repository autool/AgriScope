<script setup lang="ts">
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, ref, watch } from 'vue'

import ServiceAccessPanel from '@/components/service-sharing/ServiceAccessPanel.vue'
import ServiceCatalogPanel from '@/components/service-sharing/ServiceCatalogPanel.vue'
import ServiceRegistrationPanel from '@/components/service-sharing/ServiceRegistrationPanel.vue'
import { useServiceSharingStore } from '@/store/serviceSharingStore'
import { useUserStore } from '@/store/userStore'
import type {
  ServiceAccessRequestPayload,
  ServiceRegistrationPayload,
  SharedService,
} from '@/types/serviceSharing'

const serviceSharingStore = useServiceSharingStore()
const userStore = useUserStore()
const {
  canApproveComputed,
  canHealthCheckComputed,
  canManageComputed,
  canRequestComputed,
  loadingRef,
  mutatingRef,
  oneTimeSecretRef,
  overviewRef,
} = storeToRefs(serviceSharingStore)
const selectedServiceCodeRef = ref<string | null>(null)
const selectedServiceComputed = computed<SharedService | null>(() => (
  overviewRef.value?.services.find(
    (item) => item.service_code === selectedServiceCodeRef.value,
  ) || overviewRef.value?.services[0] || null
))

watch(() => overviewRef.value?.services, (services) => {
  if (!services?.length) {
    selectedServiceCodeRef.value = null
    return
  }
  if (!services.some((item) => item.service_code === selectedServiceCodeRef.value)) {
    selectedServiceCodeRef.value = services[0].service_code
  }
}, { deep: true })

const loadOverview = async (): Promise<void> => {
  try {
    await serviceSharingStore.load()
  } catch {
    // 请求层已显示安全错误信息，页面保留空态供用户重试或切换身份。
  }
}

watch(
  () => userStore.currentUserComputed?.user_code,
  (userCode) => {
    if (userCode) void loadOverview()
  },
  { immediate: true },
)

const runAction = async (
  action: () => Promise<void>,
  success: string,
): Promise<void> => {
  try {
    await action()
    message.success(success)
  } catch {
    // 请求层已显示安全错误信息。
  }
}

const handleRegister = (
  payload: Omit<ServiceRegistrationPayload, 'operator_code'>,
): void => {
  void runAction(
    () => serviceSharingStore.register(payload),
    '服务已登记并进入甲方审批队列',
  )
}

const handleReviewService = (
  serviceCode: string,
  decision: 'approve' | 'reject',
  comment: string,
): void => {
  void runAction(
    () => serviceSharingStore.reviewService(serviceCode, decision, comment),
    decision === 'approve' ? '共享服务已批准并激活' : '共享服务登记已驳回',
  )
}

const handleRequestAccess = (
  serviceCode: string,
  payload: Omit<ServiceAccessRequestPayload, 'operator_code'>,
): void => {
  void runAction(
    () => serviceSharingStore.requestAccess(serviceCode, payload),
    '访问申请已提交',
  )
}

const handleReviewAccess = (
  requestCode: string,
  decision: 'approve' | 'reject',
  comment: string,
): void => {
  void runAction(
    () => serviceSharingStore.reviewAccess(requestCode, decision, comment),
    decision === 'approve' ? '访问申请已批准' : '访问申请已驳回',
  )
}

</script>

<template>
  <div class="service-sharing-view">
    <section class="summary-strip">
      <span><small>REGISTERED</small><strong>{{ overviewRef?.service_count || 0 }}</strong><em>登记服务</em></span>
      <span><small>ACTIVE</small><strong>{{ overviewRef?.active_service_count || 0 }}</strong><em>已激活</em></span>
      <span><small>PENDING REVIEW</small><strong>{{ overviewRef?.pending_approval_count || 0 }}</strong><em>待甲方审批</em></span>
      <span><small>ACCESS REQUESTS</small><strong>{{ overviewRef?.pending_access_count || 0 }}</strong><em>待批访问</em></span>
      <span><small>HEALTHY</small><strong>{{ overviewRef?.healthy_service_count || 0 }}</strong><em>真实健康探测</em></span>
    </section>
    <a-spin :spinning="loadingRef" class="workspace-spin">
      <section class="workspace-grid">
        <ServiceRegistrationPanel
          :disabled="!canManageComputed"
          :loading="mutatingRef"
          @register="handleRegister"
        />
        <ServiceCatalogPanel
          :services="overviewRef?.services || []"
          :selected-code="selectedServiceComputed?.service_code || null"
          :can-approve="canApproveComputed"
          :can-manage="canManageComputed"
          :can-health-check="canHealthCheckComputed"
          :loading="mutatingRef"
          @select="selectedServiceCodeRef = $event"
          @review="handleReviewService"
          @health="(code) => runAction(() => serviceSharingStore.checkHealth(code), '健康探测已完成并记录')"
          @revoke="(code, reason) => runAction(() => serviceSharingStore.revokeService(code, reason), '服务及其活动凭证已撤销')"
        />
        <ServiceAccessPanel
          :service="selectedServiceComputed"
          :requests="overviewRef?.access_requests || []"
          :events="overviewRef?.events || []"
          :can-request="canRequestComputed"
          :can-manage="canManageComputed"
          :loading="mutatingRef"
          @request-access="handleRequestAccess"
          @review-access="handleReviewAccess"
          @revoke-credential="(code, reason) => runAction(() => serviceSharingStore.revokeCredential(code, reason), '访问凭证已撤销')"
        />
      </section>
    </a-spin>
    <a-modal
      :open="Boolean(oneTimeSecretRef)"
      title="API Key 仅显示一次"
      :footer="null"
      @cancel="serviceSharingStore.clearOneTimeSecret()"
    >
      <a-alert type="warning" show-icon message="请立即交付给获批申请方；平台数据库不保存密钥明文。" />
      <a-input-password :value="oneTimeSecretRef || ''" readonly class="secret-input" />
      <a-button type="primary" block @click="serviceSharingStore.clearOneTimeSecret()">我已安全保存</a-button>
    </a-modal>
  </div>
</template>

<style scoped>
.service-sharing-view { display: grid; grid-template-rows: auto minmax(0, 1fr); gap: 10px; height: 100%; padding: 10px; background: #eef2f0; }
.summary-strip { display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); gap: 8px; }
.summary-strip span { display: flex; flex-direction: column; padding: 10px 12px; background: #fff; border: 1px solid #dfe5e2; border-radius: 7px; }
.summary-strip small { font-size: 7px; color: #8b9791; }
.summary-strip strong { font-size: 20px; color: #347958; }
.summary-strip em { font-size: 8px; font-style: normal; color: #77867e; }
.workspace-spin { min-height: 0; }
.workspace-spin :deep(.ant-spin-container) { height: 100%; min-height: 0; }
.workspace-grid { display: grid; grid-template-columns: minmax(340px, 0.9fr) minmax(430px, 1.15fr) minmax(360px, 0.95fr); gap: 10px; height: 100%; min-height: 0; }
.secret-input { margin: 14px 0 10px; }
@media (max-width: 1250px) {
  .workspace-grid { grid-template-columns: 1fr 1fr; overflow: auto; }
  .workspace-grid > :last-child { grid-column: 1 / -1; min-height: 420px; }
}
</style>
