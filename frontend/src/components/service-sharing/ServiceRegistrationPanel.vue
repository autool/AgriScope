<script setup lang="ts">
import { message } from 'ant-design-vue'
import { reactive } from 'vue'

import type { ServiceRegistrationPayload } from '@/types/serviceSharing'

defineProps<{
  disabled: boolean
  loading: boolean
}>()

const emit = defineEmits<{
  register: [payload: Omit<ServiceRegistrationPayload, 'operator_code'>]
}>()

const form = reactive<Omit<ServiceRegistrationPayload, 'operator_code'>>({
  service_code: '',
  service_name: '',
  service_type: 'rest',
  endpoint_url: '',
  health_check_url: '',
  documentation_url: '',
  resource_type: 'external_api',
  resource_code: '',
  resource_checksum_sha256: null,
  data_classification: 'public',
  exposure_scope: 'public',
  auth_mode: 'none',
  owner_department: '',
})

const submit = (): void => {
  const required = [
    form.service_code,
    form.service_name,
    form.endpoint_url,
    form.health_check_url,
    form.documentation_url,
    form.resource_code,
    form.owner_department,
  ]
  if (required.some((item) => !item.trim())) {
    message.warning('请完整填写服务、资源、文档和责任单位信息')
    return
  }
  if (form.resource_type !== 'external_api' && !form.resource_checksum_sha256?.trim()) {
    message.warning('内部成果发布必须填写数据库实体对应的 SHA-256')
    return
  }
  emit('register', {
    ...form,
    service_code: form.service_code.trim(),
    service_name: form.service_name.trim(),
    endpoint_url: form.endpoint_url.trim(),
    health_check_url: form.health_check_url.trim(),
    documentation_url: form.documentation_url.trim(),
    resource_code: form.resource_code.trim(),
    resource_checksum_sha256: form.resource_checksum_sha256?.trim() || null,
    owner_department: form.owner_department.trim(),
  })
}
</script>

<template>
  <section class="registration-panel">
    <header>
      <span><small>SERVICE REGISTRATION</small><strong>受控服务登记</strong></span>
      <a-tag color="blue">登记后需甲方审批</a-tag>
    </header>
    <a-alert
      v-if="disabled"
      type="info"
      show-icon
      message="当前身份可查看服务目录，但只有项目负责人可登记服务。"
    />
    <div class="form-grid">
      <label><span>服务编号</span><a-input v-model:value="form.service_code" placeholder="例如 HLJ-PUBLIC-STAC" /></label>
      <label><span>服务名称</span><a-input v-model:value="form.service_name" /></label>
      <label><span>服务类型</span><a-select v-model:value="form.service_type" :options="[{value:'stac',label:'STAC'},{value:'wms',label:'WMS'},{value:'wmts',label:'WMTS'},{value:'wfs',label:'WFS'},{value:'rest',label:'REST'},{value:'download',label:'下载服务'}]" /></label>
      <label><span>资源类型</span><a-select v-model:value="form.resource_type" :options="[{value:'external_api',label:'外部公开 API'},{value:'imagery',label:'影像实体'},{value:'vector',label:'矢量资产'},{value:'thematic_map',label:'专题图'},{value:'delivery',label:'成果包'},{value:'statistics',label:'统计资产'},{value:'other',label:'其他登记资产'}]" /></label>
      <label class="wide"><span>服务地址</span><a-input v-model:value="form.endpoint_url" placeholder="https://..." /></label>
      <label class="wide"><span>健康检查地址</span><a-input v-model:value="form.health_check_url" placeholder="必须是可真实探测的 HTTP(S) 地址" /></label>
      <label class="wide"><span>接口文档地址</span><a-input v-model:value="form.documentation_url" placeholder="https://..." /></label>
      <label><span>资源编号</span><a-input v-model:value="form.resource_code" /></label>
      <label><span>资源 SHA-256</span><a-input v-model:value="form.resource_checksum_sha256" :disabled="form.resource_type === 'external_api'" placeholder="外部 API 可留空" /></label>
      <label><span>数据密级</span><a-select v-model:value="form.data_classification" :options="[{value:'public',label:'公开'},{value:'internal',label:'内部'},{value:'confidential',label:'涉密'}]" /></label>
      <label><span>暴露范围</span><a-select v-model:value="form.exposure_scope" :options="[{value:'public',label:'公共'},{value:'project',label:'项目内'},{value:'restricted',label:'受限授权'}]" /></label>
      <label><span>鉴权方式</span><a-select v-model:value="form.auth_mode" :options="[{value:'none',label:'无鉴权'},{value:'api_key',label:'API Key'},{value:'oauth2',label:'OAuth2'},{value:'network_whitelist',label:'网络白名单'}]" /></label>
      <label><span>责任单位</span><a-input v-model:value="form.owner_department" /></label>
    </div>
    <a-button
      type="primary"
      block
      :disabled="disabled"
      :loading="loading"
      @click="submit"
    >
      登记并提交审批
    </a-button>
  </section>
</template>

<style scoped>
.registration-panel { display: flex; height: 100%; min-height: 0; flex-direction: column; gap: 10px; padding: 14px; overflow: auto; background: #fff; border: 1px solid #dfe5e2; border-radius: 8px; }
header { display: flex; align-items: center; justify-content: space-between; }
header span { display: flex; flex-direction: column; }
header small { font-size: 8px; color: #87948d; }
header strong { font-size: 13px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.form-grid label { display: grid; gap: 4px; font-size: 8px; color: #6f7e76; }
.form-grid :deep(.ant-select) { width: 100%; }
.wide { grid-column: 1 / -1; }
</style>
