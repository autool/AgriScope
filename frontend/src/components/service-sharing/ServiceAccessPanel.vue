<script setup lang="ts">
import { message } from 'ant-design-vue'
import { computed, reactive, ref, watch } from 'vue'

import type {
  ServiceAccessRequest,
  ServiceAccessRequestPayload,
  ServiceUsageEvent,
  SharedService,
} from '@/types/serviceSharing'

const props = defineProps<{
  service: SharedService | null
  requests: ServiceAccessRequest[]
  events: ServiceUsageEvent[]
  canRequest: boolean
  canManage: boolean
  loading: boolean
}>()

const emit = defineEmits<{
  requestAccess: [serviceCode: string, payload: Omit<ServiceAccessRequestPayload, 'operator_code'>]
  reviewAccess: [requestCode: string, decision: 'approve' | 'reject', comment: string]
  revokeCredential: [credentialCode: string, reason: string]
}>()

const accessForm = reactive({
  applicantOrganization: '',
  purpose: '',
  requestedUntil: '',
})
const modalOpenRef = ref<boolean>(false)
const modalModeRef = ref<'approve' | 'reject' | 'revoke'>('approve')
const modalRequestRef = ref<ServiceAccessRequest | null>(null)
const modalCommentRef = ref<string>('')
const selectedRequestsComputed = computed<ServiceAccessRequest[]>(() => (
  props.service
    ? props.requests.filter((item) => item.service_code === props.service?.service_code)
    : props.requests
))
const selectedEventsComputed = computed<ServiceUsageEvent[]>(() => (
  props.service
    ? props.events.filter((item) => item.service_code === props.service?.service_code)
    : props.events
))

watch(() => props.service?.service_code, () => {
  accessForm.purpose = ''
})

const submitAccess = (): void => {
  if (!props.service) return
  if (
    !accessForm.applicantOrganization.trim()
    || accessForm.purpose.trim().length < 8
    || !accessForm.requestedUntil
  ) {
    message.warning('请填写申请单位、具体用途和访问截止日期')
    return
  }
  emit('requestAccess', props.service.service_code, {
    applicant_organization: accessForm.applicantOrganization.trim(),
    purpose: accessForm.purpose.trim(),
    requested_until: accessForm.requestedUntil,
  })
}

const openReview = (
  request: ServiceAccessRequest,
  mode: 'approve' | 'reject' | 'revoke',
): void => {
  modalRequestRef.value = request
  modalModeRef.value = mode
  modalCommentRef.value = mode === 'approve'
    ? '申请用途、期限和访问范围符合项目共享要求'
    : ''
  modalOpenRef.value = true
}

const submitReview = (): void => {
  const request = modalRequestRef.value
  const comment = modalCommentRef.value.trim()
  if (!request || comment.length < 4) return
  if (modalModeRef.value === 'revoke') {
    if (request.credential) {
      emit('revokeCredential', request.credential.credential_code, comment)
    }
  } else {
    emit('reviewAccess', request.request_code, modalModeRef.value, comment)
  }
  modalOpenRef.value = false
}

const statusColor = (status: string): string => ({
  pending: 'gold',
  approved: 'green',
  rejected: 'red',
  revoked: 'default',
  expired: 'default',
}[status] || 'default')
</script>

<template>
  <section class="access-panel">
    <header><span><small>ACCESS & AUDIT</small><strong>访问申请与调用审计</strong></span><a-tag>{{ selectedRequestsComputed.length }} 申请</a-tag></header>
    <a-empty v-if="!service" description="选择一个服务查看访问与审计" />
    <template v-else>
      <div class="selected-service">
        <strong>{{ service.service_name }}</strong>
        <small>{{ service.auth_mode }} · {{ service.exposure_scope }} · {{ service.data_classification }}</small>
      </div>
      <a-divider>申请访问</a-divider>
      <div class="access-form">
        <a-input v-model:value="accessForm.applicantOrganization" placeholder="申请单位" />
        <input v-model="accessForm.requestedUntil" type="date" class="date-input">
        <a-textarea v-model:value="accessForm.purpose" :rows="2" placeholder="具体业务用途与调用范围" />
        <a-button
          type="primary"
          block
          :disabled="!canRequest || service.status !== 'active'"
          :loading="loading"
          @click="submitAccess"
        >
          提交访问申请
        </a-button>
      </div>
      <a-divider>申请队列</a-divider>
      <div v-if="selectedRequestsComputed.length" class="request-list">
        <article v-for="request in selectedRequestsComputed" :key="request.request_code">
          <div><strong>{{ request.applicant_organization }}</strong><a-tag :color="statusColor(request.status)">{{ request.status }}</a-tag></div>
          <small>{{ request.request_code }} · {{ request.applicant }} · 至 {{ request.requested_until }}</small>
          <p>{{ request.purpose }}</p>
          <code v-if="request.credential">{{ request.credential.credential_code }} · 末四位 {{ request.credential.secret_last_four }} · {{ request.credential.status }}</code>
          <div v-if="canManage" class="request-actions">
            <a-button
              v-if="request.status === 'pending'"
              size="small"
              type="primary"
              @click="openReview(request, 'approve')"
            >
              批准
            </a-button>
            <a-button
              v-if="request.status === 'pending'"
              size="small"
              danger
              @click="openReview(request, 'reject')"
            >
              驳回
            </a-button>
            <a-button
              v-if="request.credential?.status === 'active'"
              size="small"
              danger
              @click="openReview(request, 'revoke')"
            >
              撤销凭证
            </a-button>
          </div>
        </article>
      </div>
      <a-empty v-else :image-style="{ height: '36px' }" description="该服务尚无访问申请" />
      <a-divider>最近审计</a-divider>
      <div v-if="selectedEventsComputed.length" class="event-list">
        <article v-for="(event, index) in selectedEventsComputed.slice(0, 12)" :key="`${event.created_at}-${index}`">
          <i /><span><strong>{{ event.event_type }}</strong><small>{{ event.actor }} · {{ new Date(event.created_at).toLocaleString('zh-CN') }}</small></span><em v-if="event.response_status">HTTP {{ event.response_status }}</em>
        </article>
      </div>
      <a-empty v-else :image-style="{ height: '36px' }" description="尚无服务审计事件" />
    </template>
    <a-modal
      v-model:open="modalOpenRef"
      title="访问审批与凭证撤销"
      :confirm-loading="loading"
      @ok="submitReview"
    >
      <a-textarea v-model:value="modalCommentRef" :rows="4" placeholder="填写审批依据或撤销原因" />
    </a-modal>
  </section>
</template>

<style scoped>
.access-panel { height: 100%; min-height: 0; padding: 14px; overflow: auto; background: #fff; border: 1px solid #dfe5e2; border-radius: 8px; }
header, .request-list article > div:first-child, .request-actions { display: flex; align-items: center; justify-content: space-between; }
header span, .selected-service { display: flex; flex-direction: column; }
header small { font-size: 8px; color: #87948d; }
header strong { font-size: 13px; }
.selected-service { gap: 2px; padding: 9px; margin-top: 10px; background: #f0f7f3; border: 1px solid #dce9e1; border-radius: 6px; }
.selected-service strong { font-size: 10px; }
.selected-service small { font-size: 8px; color: #76847c; }
.access-form { display: grid; grid-template-columns: 1fr 150px; gap: 7px; }
.access-form :deep(.ant-input-textarea), .access-form :deep(.ant-btn) { grid-column: 1 / -1; }
.date-input { min-width: 0; padding: 4px 8px; font: inherit; border: 1px solid #d9d9d9; border-radius: 6px; }
.request-list { display: grid; gap: 7px; }
.request-list article { padding: 9px; background: #f8faf9; border: 1px solid #e4e9e6; border-radius: 6px; }
.request-list strong { font-size: 9px; }
.request-list small, .request-list p, .request-list code { display: block; overflow: hidden; font-size: 8px; color: #7d8983; text-overflow: ellipsis; white-space: nowrap; }
.request-list p { margin: 4px 0; }
.request-list code { color: #39694f; }
.request-actions { justify-content: flex-start; gap: 5px; margin-top: 7px; }
.event-list { display: grid; gap: 5px; }
.event-list article { display: grid; grid-template-columns: 8px minmax(0, 1fr) auto; gap: 7px; align-items: center; padding: 6px 0; border-bottom: 1px solid #edf0ee; }
.event-list i { width: 6px; height: 6px; background: #4a9b70; border-radius: 50%; }
.event-list span { display: flex; min-width: 0; flex-direction: column; }
.event-list strong { font-size: 8px; }
.event-list small, .event-list em { font-size: 7px; font-style: normal; color: #839088; }
</style>
