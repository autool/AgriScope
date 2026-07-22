<script setup lang="ts">
import {
  CheckOutlined,
  CloseOutlined,
  LinkOutlined,
  ReloadOutlined,
  StopOutlined,
} from '@ant-design/icons-vue'
import { computed, ref } from 'vue'

import type { SharedService } from '@/types/serviceSharing'

defineProps<{
  services: SharedService[]
  selectedCode: string | null
  canApprove: boolean
  canManage: boolean
  canHealthCheck: boolean
  loading: boolean
}>()

const emit = defineEmits<{
  select: [serviceCode: string]
  review: [serviceCode: string, decision: 'approve' | 'reject', comment: string]
  health: [serviceCode: string]
  revoke: [serviceCode: string, reason: string]
}>()

const modalOpenRef = ref<boolean>(false)
const modalModeRef = ref<'approve' | 'reject' | 'revoke'>('approve')
const modalServiceRef = ref<SharedService | null>(null)
const modalCommentRef = ref<string>('')
const modalTitleComputed = computed<string>(() => ({
  approve: '批准共享服务',
  reject: '驳回共享服务',
  revoke: '撤销共享服务',
}[modalModeRef.value]))

const statusLabels: Record<string, string> = {
  pending_approval: '待甲方审批',
  active: '已激活',
  rejected: '已驳回',
  suspended: '已暂停',
  revoked: '已撤销',
}
const statusColors: Record<string, string> = {
  pending_approval: 'gold',
  active: 'green',
  rejected: 'red',
  suspended: 'orange',
  revoked: 'default',
}

const openModal = (
  service: SharedService,
  mode: 'approve' | 'reject' | 'revoke',
): void => {
  modalServiceRef.value = service
  modalModeRef.value = mode
  modalCommentRef.value = mode === 'approve'
    ? '服务来源、文档、密级和暴露范围符合项目共享要求'
    : ''
  modalOpenRef.value = true
}

const submitModal = (): void => {
  const service = modalServiceRef.value
  if (!service || modalCommentRef.value.trim().length < 4) return
  if (modalModeRef.value === 'revoke') {
    emit('revoke', service.service_code, modalCommentRef.value.trim())
  } else {
    emit('review', service.service_code, modalModeRef.value, modalCommentRef.value.trim())
  }
  modalOpenRef.value = false
}
</script>

<template>
  <section class="catalog-panel">
    <header><span><small>REGISTERED SERVICES</small><strong>服务目录与健康证据</strong></span><a-tag>{{ services.length }} 项</a-tag></header>
    <div v-if="services.length" class="service-list">
      <article
        v-for="service in services"
        :key="service.service_code"
        :class="{ selected: selectedCode === service.service_code }"
        @click="emit('select', service.service_code)"
      >
        <div class="service-heading">
          <span><strong>{{ service.service_name }}</strong><small>{{ service.service_code }} · {{ service.service_type.toUpperCase() }}</small></span>
          <a-tag :color="statusColors[service.status]">{{ statusLabels[service.status] }}</a-tag>
        </div>
        <p>{{ service.endpoint_url }}</p>
        <dl>
          <div><dt>资源</dt><dd>{{ service.resource_type }} / {{ service.resource_code }}</dd></div>
          <div><dt>安全</dt><dd>{{ service.data_classification }} · {{ service.exposure_scope }} · {{ service.auth_mode }}</dd></div>
          <div><dt>健康</dt><dd>{{ service.latest_health ? `${service.latest_health.status} · ${service.latest_health.response_time_ms}ms` : '尚未探测' }}</dd></div>
          <div><dt>使用</dt><dd>{{ service.access_request_count }} 申请 · {{ service.active_credential_count }} 凭证 · {{ service.usage_count }} 调用</dd></div>
        </dl>
        <div class="actions" @click.stop>
          <a-button size="small" :href="service.documentation_url" target="_blank"><LinkOutlined /> 文档</a-button>
          <a-button
            v-if="canHealthCheck && ['active','suspended'].includes(service.status)"
            size="small"
            :loading="loading"
            @click="emit('health', service.service_code)"
          >
            <ReloadOutlined /> 健康检查
          </a-button>
          <a-button
            v-if="canApprove && service.status === 'pending_approval'"
            size="small"
            type="primary"
            @click="openModal(service, 'approve')"
          >
            <CheckOutlined /> 批准
          </a-button>
          <a-button
            v-if="canApprove && service.status === 'pending_approval'"
            size="small"
            danger
            @click="openModal(service, 'reject')"
          >
            <CloseOutlined /> 驳回
          </a-button>
          <a-button
            v-if="canManage && !['revoked','rejected'].includes(service.status)"
            size="small"
            danger
            @click="openModal(service, 'revoke')"
          >
            <StopOutlined /> 撤销
          </a-button>
        </div>
      </article>
    </div>
    <a-empty v-else description="尚未登记真实共享服务" />
    <a-modal
      v-model:open="modalOpenRef"
      :title="modalTitleComputed"
      :confirm-loading="loading"
      @ok="submitModal"
    >
      <a-textarea v-model:value="modalCommentRef" :rows="4" placeholder="填写审批依据或撤销原因" />
    </a-modal>
  </section>
</template>

<style scoped>
.catalog-panel { height: 100%; min-height: 0; padding: 14px; overflow: auto; background: #fff; border: 1px solid #dfe5e2; border-radius: 8px; }
header, .service-heading, .actions { display: flex; align-items: center; justify-content: space-between; }
header { margin-bottom: 10px; }
header span, .service-heading > span { display: flex; min-width: 0; flex-direction: column; }
header small { font-size: 8px; color: #87948d; }
header strong { font-size: 13px; }
.service-list { display: grid; gap: 8px; }
article { padding: 11px; cursor: pointer; background: #f8faf9; border: 1px solid #e2e7e4; border-radius: 7px; }
article.selected { background: #f0f7f3; border-color: #73ad8d; box-shadow: inset 3px 0 #4a9b70; }
.service-heading strong { overflow: hidden; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.service-heading small, p, dl { font-size: 8px; color: #78867f; }
p { overflow: hidden; margin: 6px 0; color: #416753; text-overflow: ellipsis; white-space: nowrap; }
dl { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 12px; margin: 0; }
dl div { display: grid; grid-template-columns: 38px minmax(0, 1fr); }
dt { color: #929d97; }
dd { overflow: hidden; margin: 0; text-overflow: ellipsis; white-space: nowrap; }
.actions { justify-content: flex-start; gap: 5px; margin-top: 9px; }
</style>
