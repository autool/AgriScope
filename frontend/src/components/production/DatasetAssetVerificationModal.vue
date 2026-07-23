<script setup lang="ts">
import { SafetyCertificateOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { computed, ref } from 'vue'

import { datasetAssetAcceptMap } from '@/components/production/datasetAssetOptions'
import type { DatasetAsset } from '@/types/production'

const props = defineProps<{
  saving: boolean
  operatorCode: string | null
}>()

const emit = defineEmits<{
  verify: [assetCode: string, file: File, verificationComment: string]
}>()

const modalOpenRef = ref<boolean>(false)
const assetRef = ref<DatasetAsset | null>(null)
const selectedFileRef = ref<File | null>(null)
const verificationCommentRef = ref<string>('')

const acceptComputed = computed<string>(() => (
  assetRef.value ? datasetAssetAcceptMap[assetRef.value.asset_type] : ''
))

const open = (asset: DatasetAsset): void => {
  assetRef.value = asset
  selectedFileRef.value = null
  verificationCommentRef.value = ''
  modalOpenRef.value = true
}

const selectFile = (event: Event): void => {
  const target = event.target as HTMLInputElement
  selectedFileRef.value = target.files?.[0] || null
}

const submit = (): void => {
  if (!props.operatorCode || !assetRef.value) {
    message.warning('当前项目身份或待核验资产尚未初始化')
    return
  }
  if (!selectedFileRef.value) {
    message.warning('请选择与登记校验值对应的实体文件')
    return
  }
  const comment = verificationCommentRef.value.trim()
  if (comment.length < 10) {
    message.warning('实体核验依据至少填写 10 个字符')
    return
  }
  emit('verify', assetRef.value.asset_code, selectedFileRef.value, comment)
}

defineExpose({
  open,
  closeAfterSaved: () => {
    modalOpenRef.value = false
    assetRef.value = null
    selectedFileRef.value = null
    verificationCommentRef.value = ''
  },
})
</script>

<template>
  <a-modal
    v-model:open="modalOpenRef"
    title="补传并核验数据资产实体"
    width="620px"
    :confirm-loading="saving"
    ok-text="计算并比对 SHA-256"
    cancel-text="取消"
    @ok="submit"
  >
    <a-alert
      type="warning"
      show-icon
      message="核验不通过也会保留审计"
      description="系统将计算实体 SHA-256 与登记值比对；不一致时保存拒绝尝试，但不会把文件发布到受控目录。"
    />
    <dl v-if="assetRef" class="asset-summary">
      <div><dt>资产</dt><dd>{{ assetRef.asset_code }} · {{ assetRef.asset_name }}</dd></div>
      <div><dt>期望 SHA-256</dt><dd><code>{{ assetRef.checksum_sha256 }}</code></dd></div>
      <div><dt>允许格式</dt><dd>{{ acceptComputed }}</dd></div>
    </dl>
    <div class="verification-form">
      <label><span>实体文件</span><input :accept="acceptComputed" type="file" @change="selectFile"></label>
      <small>{{ selectedFileRef?.name || '尚未选择文件' }}</small>
      <label><span>核验依据</span><a-textarea v-model:value="verificationCommentRef" :rows="3" placeholder="至少 10 个字符，说明文件交接来源和核验目的" /></label>
    </div>
    <div class="audit-note"><SafetyCertificateOutlined /> 当前操作人编码：{{ operatorCode || '--' }}</div>
  </a-modal>
</template>

<style scoped>
.asset-summary { display: grid; gap: 7px; padding: 10px; margin: 12px 0; background: #fafbfa; border: 1px solid #e3e9e5; border-radius: 6px; }
.asset-summary div { display: grid; grid-template-columns: 90px minmax(0, 1fr); gap: 8px; }
.asset-summary dt { font-size: 8px; color: #7a8981; }
.asset-summary dd { min-width: 0; margin: 0; overflow: hidden; font-size: 9px; color: #35443c; text-overflow: ellipsis; white-space: nowrap; }
.asset-summary code { font-size: 8px; }
.verification-form { display: grid; gap: 8px; }
.verification-form label { display: grid; grid-template-columns: 90px minmax(0, 1fr); gap: 8px; align-items: center; font-size: 9px; }
.verification-form input { min-width: 0; height: 32px; padding: 4px 8px; border: 1px solid #d9d9d9; border-radius: 6px; }
.verification-form small { padding-left: 98px; overflow: hidden; font-size: 8px; color: #718078; text-overflow: ellipsis; white-space: nowrap; }
.audit-note { padding: 9px 10px; margin-top: 12px; font-size: 8px; color: #52705f; background: #f3f7f4; border-radius: 5px; }
</style>
