<script setup lang="ts">
import {
  ApartmentOutlined,
  CloudDownloadOutlined,
  DatabaseOutlined,
  FileProtectOutlined,
  LinkOutlined,
  PlusOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { computed, ref } from 'vue'

import DatasetAssetRegisterModal from '@/components/production/DatasetAssetRegisterModal.vue'
import DatasetAssetVerificationModal from '@/components/production/DatasetAssetVerificationModal.vue'
import { datasetAssetTypeLabels } from '@/components/production/datasetAssetOptions'
import type {
  DatasetAsset,
  DatasetAssetCreatePayload,
  DatasetAssetUploadPayload,
} from '@/types/production'

const props = defineProps<{
  assets: DatasetAsset[]
  saving: boolean
  canManage: boolean
  operatorCode: string | null
}>()

const emit = defineEmits<{
  registerReference: [payload: DatasetAssetCreatePayload]
  uploadEntity: [payload: DatasetAssetUploadPayload, file: File]
  verifyEntity: [assetCode: string, file: File, verificationComment: string]
  downloadEntity: [asset: DatasetAsset]
}>()

const registerModalRef = ref<InstanceType<typeof DatasetAssetRegisterModal> | null>(null)
const verificationModalRef = ref<InstanceType<typeof DatasetAssetVerificationModal> | null>(null)

const sourceTypeCountComputed = computed<number>(() => (
  new Set(props.assets.map((item) => item.source_name)).size
))

const verificationLabel = (asset: DatasetAsset): string => {
  if (asset.verification_status === 'verified') return '实体已核验'
  if (asset.verification_status === 'rejected') return '核验不通过'
  if (asset.verification_status === 'unavailable') return '来源不可用'
  return '待实体核验'
}

const verificationColor = (asset: DatasetAsset): string => {
  if (asset.verification_status === 'verified') return 'green'
  if (asset.verification_status === 'pending') return 'orange'
  return 'red'
}

const formatBytes = (value: number | null): string => {
  if (!value) return '--'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = value
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size.toFixed(index === 0 ? 0 : 2)} ${units[index]}`
}

const openRegister = (): void => {
  if (!props.canManage) {
    message.warning('当前项目身份无权登记多源数据资产')
    return
  }
  registerModalRef.value?.open()
}

const openVerification = (asset: DatasetAsset): void => {
  if (!props.canManage) {
    message.warning('当前项目身份无权核验多源数据资产')
    return
  }
  verificationModalRef.value?.open(asset)
}

defineExpose({
  closeRegisterAfterSaved: () => registerModalRef.value?.closeAfterSaved(),
  closeVerificationAfterSaved: () => verificationModalRef.value?.closeAfterSaved(),
})
</script>

<template>
  <section class="dataset-panel">
    <header class="panel-heading">
      <span>
        <DatabaseOutlined />
        <i><small>MULTI-SOURCE CATALOG</small><strong>多源生产数据目录</strong></i>
      </span>
      <a-button type="primary" :disabled="!canManage" @click="openRegister">
        <PlusOutlined /> 登记数据资产
      </a-button>
    </header>

    <div class="catalog-summary">
      <span><strong>{{ assets.length }}</strong><small>登记资产</small></span>
      <span><strong>{{ sourceTypeCountComputed }}</strong><small>数据来源</small></span>
      <span><strong>{{ assets.filter((item) => item.verification_status === 'verified').length }}</strong><small>实体已核验</small></span>
      <span><strong>{{ assets.filter((item) => item.data_status === 'demo').length }}</strong><small>明确演示</small></span>
    </div>

    <a-empty
      v-if="!assets.length"
      class="empty-state"
      description="尚未登记多源生产数据；可上传实体直接核验，也可先登记公开来源并在后续补传"
    />
    <div v-else class="asset-grid">
      <article v-for="asset in assets" :key="asset.asset_code">
        <header>
          <span><DatabaseOutlined /><i><strong>{{ asset.asset_name }}</strong><small>{{ asset.asset_code }}</small></i></span>
          <a-tag :color="verificationColor(asset)">{{ verificationLabel(asset) }}</a-tag>
        </header>
        <div class="asset-tags">
          <a-tag>{{ datasetAssetTypeLabels[asset.asset_type] }}</a-tag>
          <a-tag :color="asset.data_status === 'demo' ? 'purple' : 'blue'">
            {{ asset.data_status === 'demo' ? '演示数据' : '业务数据' }}
          </a-tag>
          <a-tag>{{ asset.security_classification }}</a-tag>
        </div>
        <dl>
          <div><dt>来源</dt><dd>{{ asset.source_name }}</dd></div>
          <div><dt>版本</dt><dd>{{ asset.source_version }}</dd></div>
          <div><dt>坐标系</dt><dd>{{ asset.crs || '--' }}</dd></div>
          <div><dt>登记人</dt><dd>{{ asset.registered_by }}</dd></div>
        </dl>
        <p><LinkOutlined /> {{ asset.source_uri }}</p>
        <div class="checksum-row"><small>目录 SHA-256</small><code>{{ asset.checksum_sha256 }}</code></div>

        <section v-if="asset.verification_status === 'verified'" class="physical-evidence">
          <strong><FileProtectOutlined /> 受控实体证据</strong>
          <dl>
            <div><dt>文件</dt><dd>{{ asset.physical_original_filename }}</dd></div>
            <div><dt>大小</dt><dd>{{ formatBytes(asset.physical_file_size_bytes) }}</dd></div>
            <div><dt>媒体类型</dt><dd>{{ asset.physical_media_type }}</dd></div>
            <div><dt>核验人</dt><dd>{{ asset.verified_by }}</dd></div>
          </dl>
          <p>{{ asset.verification_comment }}</p>
        </section>
        <a-alert
          v-else-if="asset.verification_status === 'rejected'"
          class="verification-state"
          type="error"
          show-icon
          message="上次实体核验未通过"
          description="拒绝尝试已留痕，文件未发布；请选择与登记 SHA-256 对应的正确实体再次核验。"
        />
        <a-alert
          v-else
          class="verification-state"
          type="warning"
          show-icon
          message="仅有来源登记，尚无可复核实体"
        />

        <div v-if="asset.parent_asset_codes.length" class="lineage">
          <ApartmentOutlined /> 派生自 {{ asset.parent_asset_codes.join('、') }}
        </div>
        <footer>
          <a-button
            v-if="asset.verification_status !== 'verified'"
            size="small"
            :disabled="!canManage"
            @click="openVerification(asset)"
          >
            <FileProtectOutlined /> 补传核验
          </a-button>
          <a-button
            v-else
            size="small"
            :disabled="!canManage"
            @click="emit('downloadEntity', asset)"
          >
            <CloudDownloadOutlined /> 复核并下载
          </a-button>
        </footer>
      </article>
    </div>

    <DatasetAssetRegisterModal
      ref="registerModalRef"
      :assets="assets"
      :saving="saving"
      :operator-code="operatorCode"
      @register-reference="emit('registerReference', $event)"
      @upload-entity="(payload, file) => emit('uploadEntity', payload, file)"
    />
    <DatasetAssetVerificationModal
      ref="verificationModalRef"
      :saving="saving"
      :operator-code="operatorCode"
      @verify="(assetCode, file, comment) => emit('verifyEntity', assetCode, file, comment)"
    />
  </section>
</template>

<style scoped>
.dataset-panel { min-height: 420px; }
.panel-heading, .panel-heading > span, .asset-grid article header, .asset-grid article header > span, .asset-grid footer { display: flex; align-items: center; }
.panel-heading { justify-content: space-between; margin-bottom: 10px; }
.panel-heading > span { gap: 9px; color: #3f8662; }
.panel-heading > span > :first-child { font-size: 22px; }
.panel-heading i, .asset-grid article header i { display: flex; flex-direction: column; font-style: normal; }
.panel-heading small, .asset-grid small { font-size: 8px; color: #89958f; }
.panel-heading strong { font-size: 13px; color: #29372f; }
.catalog-summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 10px; }
.catalog-summary span { display: flex; flex-direction: column; padding: 10px 12px; background: #f7f9f8; border: 1px solid #e5ebe7; border-radius: 6px; }
.catalog-summary strong { font-size: 17px; color: #397b58; }
.catalog-summary small { font-size: 8px; color: #7e8b84; }
.empty-state { padding: 70px 20px; background: #fafbfa; border: 1px dashed #d9e1dc; border-radius: 7px; }
.asset-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.asset-grid article { min-width: 0; padding: 12px; background: #fafbfa; border: 1px solid #e0e7e3; border-radius: 7px; }
.asset-grid article header { justify-content: space-between; gap: 8px; }
.asset-grid article header > span { min-width: 0; gap: 7px; color: #438463; }
.asset-grid article header i { min-width: 0; }
.asset-grid article header strong { overflow: hidden; font-size: 10px; color: #2c3932; text-overflow: ellipsis; white-space: nowrap; }
.asset-tags { margin: 8px 0; }
.asset-grid dl { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; margin: 0; }
.asset-grid dl div { min-width: 0; padding: 6px; background: #fff; border-radius: 4px; }
.asset-grid dt { font-size: 7px; color: #89958f; }
.asset-grid dd { margin: 2px 0 0; overflow: hidden; font-size: 8px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.asset-grid > article > p { margin: 8px 0 4px; overflow: hidden; font-size: 8px; color: #65736c; text-overflow: ellipsis; white-space: nowrap; }
.checksum-row { min-width: 0; padding: 6px; background: #f3f6f4; border-radius: 4px; }
.checksum-row code { display: block; overflow: hidden; font-size: 7px; color: #617169; text-overflow: ellipsis; white-space: nowrap; }
.physical-evidence { padding: 8px; margin-top: 8px; background: #f1f8f4; border: 1px solid #d9eadf; border-radius: 5px; }
.physical-evidence > strong { font-size: 8px; color: #397b58; }
.physical-evidence dl { margin-top: 6px; }
.physical-evidence p { margin: 6px 0 0; font-size: 8px; color: #5e7166; }
.verification-state { margin-top: 8px; }
.verification-state :deep(.ant-alert-message), .verification-state :deep(.ant-alert-description) { font-size: 8px; }
.lineage { padding-top: 7px; margin-top: 7px; font-size: 8px; color: #397b58; border-top: 1px dashed #d9e2dc; }
.asset-grid footer { justify-content: flex-end; margin-top: 8px; }
@media (max-width: 920px) {
  .asset-grid { grid-template-columns: 1fr; }
  .catalog-summary { grid-template-columns: repeat(2, 1fr); }
}
</style>
