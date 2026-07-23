<script setup lang="ts">
import { SafetyCertificateOutlined, UploadOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { computed, ref } from 'vue'

import {
  datasetAssetAcceptMap,
  datasetAssetTypeOptions,
} from '@/components/production/datasetAssetOptions'
import type {
  DatasetAsset,
  DatasetAssetCreatePayload,
  DatasetAssetMetadataPayload,
  DatasetAssetType,
  DatasetAssetUploadPayload,
  ProductionDataStatus,
  SecurityClassification,
} from '@/types/production'

type RegisterMode = 'upload' | 'reference'

const props = defineProps<{
  assets: DatasetAsset[]
  saving: boolean
  operatorCode: string | null
}>()

const emit = defineEmits<{
  registerReference: [payload: DatasetAssetCreatePayload]
  uploadEntity: [payload: DatasetAssetUploadPayload, file: File]
}>()

const modalOpenRef = ref<boolean>(false)
const modeRef = ref<RegisterMode>('upload')
const assetCodeRef = ref<string>('')
const assetNameRef = ref<string>('')
const assetTypeRef = ref<DatasetAssetType>('imagery')
const sourceNameRef = ref<string>('')
const sourceUriRef = ref<string>('')
const sourceVersionRef = ref<string>('')
const checksumRef = ref<string>('')
const crsRef = ref<string>('EPSG:4326')
const bboxTextRef = ref<string>('')
const timeStartRef = ref<string>('')
const timeEndRef = ref<string>('')
const securityRef = ref<SecurityClassification>('internal')
const dataStatusRef = ref<ProductionDataStatus>('operational')
const parentCodesRef = ref<string[]>([])
const verificationCommentRef = ref<string>('')
const selectedFileRef = ref<File | null>(null)

const acceptComputed = computed<string>(() => (
  datasetAssetAcceptMap[assetTypeRef.value]
))

const reset = (): void => {
  modeRef.value = 'upload'
  assetCodeRef.value = ''
  assetNameRef.value = ''
  assetTypeRef.value = 'imagery'
  sourceNameRef.value = ''
  sourceUriRef.value = ''
  sourceVersionRef.value = ''
  checksumRef.value = ''
  crsRef.value = 'EPSG:4326'
  bboxTextRef.value = ''
  timeStartRef.value = ''
  timeEndRef.value = ''
  securityRef.value = 'internal'
  dataStatusRef.value = 'operational'
  parentCodesRef.value = []
  verificationCommentRef.value = ''
  selectedFileRef.value = null
}

const open = (): void => {
  modalOpenRef.value = true
}

const parseBbox = (): [number, number, number, number] | null => {
  if (!bboxTextRef.value.trim()) return null
  const values = bboxTextRef.value.split(',').map((value) => Number(value.trim()))
  if (values.length !== 4 || values.some((value) => !Number.isFinite(value))) {
    message.warning('WGS84 范围需填写 minLon,minLat,maxLon,maxLat')
    return null
  }
  const [minLon, minLat, maxLon, maxLat] = values
  if (minLon >= maxLon || minLat >= maxLat) {
    message.warning('WGS84 范围最小坐标必须小于最大坐标')
    return null
  }
  return [minLon, minLat, maxLon, maxLat]
}

const toIsoTime = (value: string): string | null => (
  value ? new Date(value).toISOString() : null
)

const buildMetadata = (): DatasetAssetUploadPayload | null => {
  const operatorCode = props.operatorCode
  if (!operatorCode) {
    message.warning('当前项目身份尚未初始化')
    return null
  }
  if (
    !assetCodeRef.value.trim()
    || !assetNameRef.value.trim()
    || !sourceNameRef.value.trim()
    || !sourceUriRef.value.trim()
    || !sourceVersionRef.value.trim()
  ) {
    message.warning('请完整填写资产编号、名称和来源信息')
    return null
  }
  const bbox = parseBbox()
  if (bboxTextRef.value.trim() && !bbox) return null
  const timeStart = toIsoTime(timeStartRef.value)
  const timeEnd = toIsoTime(timeEndRef.value)
  if (timeStart && timeEnd && timeEnd < timeStart) {
    message.warning('数据结束时间不得早于开始时间')
    return null
  }
  return {
    asset_code: assetCodeRef.value.trim(),
    asset_name: assetNameRef.value.trim(),
    asset_type: assetTypeRef.value,
    source_name: sourceNameRef.value.trim(),
    source_uri: sourceUriRef.value.trim(),
    source_version: sourceVersionRef.value.trim(),
    crs: crsRef.value.trim() || null,
    extent_bbox: bbox,
    time_start: timeStart,
    time_end: timeEnd,
    security_classification: securityRef.value,
    data_status: dataStatusRef.value,
    parent_asset_codes: parentCodesRef.value,
    lineage_relation_type: 'derived_from',
    process_code: null,
    metadata: {},
    operator_code: operatorCode,
    verification_comment: verificationCommentRef.value.trim(),
  }
}

const selectFile = (event: Event): void => {
  const target = event.target as HTMLInputElement
  selectedFileRef.value = target.files?.[0] || null
}

const submit = (): void => {
  const metadata = buildMetadata()
  if (!metadata) return
  if (modeRef.value === 'upload') {
    if (!selectedFileRef.value) {
      message.warning('请选择需要受控入库的数据实体文件')
      return
    }
    if (metadata.verification_comment.length < 10) {
      message.warning('实体核验依据至少填写 10 个字符')
      return
    }
    emit('uploadEntity', metadata, selectedFileRef.value)
    return
  }
  const checksum = checksumRef.value.trim().toLowerCase()
  if (!/^[a-f0-9]{64}$/.test(checksum)) {
    message.warning('外部来源 SHA-256 必须是 64 位十六进制校验值')
    return
  }
  const baseMetadata = Object.fromEntries(
    Object.entries(metadata).filter(([key]) => key !== 'verification_comment'),
  ) as unknown as DatasetAssetMetadataPayload
  emit('registerReference', {
    ...baseMetadata,
    checksum_sha256: checksum,
  })
}

defineExpose({
  open,
  closeAfterSaved: () => {
    modalOpenRef.value = false
    reset()
  },
})
</script>

<template>
  <a-modal
    v-model:open="modalOpenRef"
    title="登记多源生产数据资产"
    width="760px"
    :confirm-loading="saving"
    :ok-text="modeRef === 'upload' ? '上传、核验并登记' : '登记为待核验'"
    cancel-text="取消"
    @ok="submit"
  >
    <a-segmented
      v-model:value="modeRef"
      block
      :options="[
        { label: '上传实体并登记', value: 'upload' },
        { label: '仅登记外部来源', value: 'reference' },
      ]"
    />
    <a-alert
      class="mode-alert"
      :type="modeRef === 'upload' ? 'success' : 'warning'"
      show-icon
      :message="modeRef === 'upload' ? '服务端实体核验' : '外部来源待核验'"
      :description="modeRef === 'upload'
        ? '文件将临时落盘，服务端检查格式与结构、计算 SHA-256，并仅在数据库事务成功后保留受控实体。'
        : '调用方填写的 SHA-256 只作为后续核验期望值；没有物理实体时状态保持待核验，不能用于生产批次。'"
    />

    <div class="asset-form">
      <label><span>资产编号</span><a-input v-model:value="assetCodeRef" placeholder="字母、数字、下划线或连字符" /></label>
      <label><span>资产名称</span><a-input v-model:value="assetNameRef" /></label>
      <label><span>数据类型</span><a-select v-model:value="assetTypeRef"><a-select-option v-for="option in datasetAssetTypeOptions" :key="option[0]" :value="option[0]">{{ option[1] }}</a-select-option></a-select></label>
      <label><span>来源名称</span><a-input v-model:value="sourceNameRef" placeholder="公开机构、业务系统或设备来源" /></label>
      <label class="wide"><span>来源地址</span><a-input v-model:value="sourceUriRef" placeholder="公开 URL、交接单号或来源系统 URI" /></label>
      <label><span>来源版本</span><a-input v-model:value="sourceVersionRef" placeholder="发布日期、版本号或批次" /></label>
      <label><span>数据坐标系</span><a-input v-model:value="crsRef" placeholder="如 EPSG:4326 / EPSG:4490" /></label>
      <label><span>开始时间</span><input v-model="timeStartRef" type="datetime-local"></label>
      <label><span>结束时间</span><input v-model="timeEndRef" type="datetime-local"></label>
      <label class="wide"><span>WGS84 范围</span><a-input v-model:value="bboxTextRef" placeholder="可选：minLon,minLat,maxLon,maxLat" /></label>
      <label><span>数据密级</span><a-select v-model:value="securityRef"><a-select-option value="public">公开</a-select-option><a-select-option value="internal">内部</a-select-option><a-select-option value="restricted">受限</a-select-option><a-select-option value="confidential">涉密</a-select-option></a-select></label>
      <label><span>数据属性</span><a-select v-model:value="dataStatusRef"><a-select-option value="operational">业务数据</a-select-option><a-select-option value="demo">明确演示数据</a-select-option></a-select></label>
      <label class="wide"><span>父资产血缘</span><a-select
        v-model:value="parentCodesRef"
        mode="multiple"
        allow-clear
        placeholder="可选：选择派生来源资产"
      ><a-select-option v-for="asset in assets" :key="asset.asset_code" :value="asset.asset_code">{{ asset.asset_code }} · {{ asset.asset_name }}</a-select-option></a-select></label>

      <label v-if="modeRef === 'reference'" class="wide"><span>期望 SHA-256</span><a-input v-model:value="checksumRef" placeholder="64 位内容校验值，后续补传时重新计算比对" /></label>
      <label v-else class="wide file-field">
        <span>实体文件</span>
        <input :accept="acceptComputed" type="file" @change="selectFile">
        <em><UploadOutlined /> {{ selectedFileRef?.name || `允许格式：${acceptComputed}` }}</em>
      </label>
      <label v-if="modeRef === 'upload'" class="wide"><span>核验依据</span><a-textarea v-model:value="verificationCommentRef" :rows="2" placeholder="至少 10 个字符，说明文件交接、来源和本次入库用途" /></label>
    </div>
    <div class="audit-note"><SafetyCertificateOutlined /> 当前操作人编码：{{ operatorCode || '--' }}</div>
  </a-modal>
</template>

<style scoped>
.mode-alert { margin-top: 12px; }
.asset-form { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 14px; }
.asset-form label { display: grid; grid-template-columns: 86px minmax(0, 1fr); gap: 8px; align-items: center; font-size: 9px; }
.asset-form label > span { color: #4d5f55; }
.asset-form .wide { grid-column: 1 / -1; }
.asset-form input[type='datetime-local'], .asset-form input[type='file'] { min-width: 0; height: 32px; padding: 4px 8px; color: #35463d; background: #fff; border: 1px solid #d9d9d9; border-radius: 6px; }
.file-field { grid-template-columns: 86px minmax(0, 1fr); }
.file-field em { grid-column: 2; overflow: hidden; font-size: 8px; font-style: normal; color: #6f8077; text-overflow: ellipsis; white-space: nowrap; }
.audit-note { padding: 9px 10px; margin-top: 12px; font-size: 8px; color: #52705f; background: #f3f7f4; border-radius: 5px; }
@media (max-width: 920px) {
  .asset-form { grid-template-columns: 1fr; }
  .asset-form .wide { grid-column: auto; }
}
</style>
