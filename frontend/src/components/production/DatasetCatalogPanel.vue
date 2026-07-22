<script setup lang="ts">
import {
  ApartmentOutlined,
  DatabaseOutlined,
  LinkOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { computed, ref } from 'vue'

import type {
  DatasetAsset,
  DatasetAssetCreatePayload,
  DatasetAssetType,
  ProductionDataStatus,
  SecurityClassification,
} from '@/types/production'

const props = defineProps<{
  assets: DatasetAsset[]
  saving: boolean
  canManage: boolean
  operatorCode: string | null
}>()

const emit = defineEmits<{
  register: [payload: DatasetAssetCreatePayload]
}>()

const modalOpenRef = ref<boolean>(false)
const assetCodeRef = ref<string>('')
const assetNameRef = ref<string>('')
const assetTypeRef = ref<DatasetAssetType>('imagery')
const sourceNameRef = ref<string>('')
const sourceUriRef = ref<string>('')
const sourceVersionRef = ref<string>('')
const checksumRef = ref<string>('')
const crsRef = ref<string>('EPSG:4326')
const bboxTextRef = ref<string>('')
const securityRef = ref<SecurityClassification>('internal')
const dataStatusRef = ref<ProductionDataStatus>('operational')
const parentCodesRef = ref<string[]>([])

const assetTypeOptions = [
  ['imagery', '卫星/航空影像'],
  ['vector', '矢量数据'],
  ['table', '表格数据'],
  ['dem', 'DEM 高程'],
  ['control', '控制资料'],
  ['weather', '气象数据'],
  ['management', '管理信息'],
  ['uav', '无人机数据'],
  ['iot', '物联网数据'],
] as const

const assetTypeLabels = Object.fromEntries(assetTypeOptions) as Record<DatasetAssetType, string>

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

const sourceTypeCountComputed = computed<number>(() => (
  new Set(props.assets.map((item) => item.source_name)).size
))

const resetForm = (): void => {
  assetCodeRef.value = ''
  assetNameRef.value = ''
  assetTypeRef.value = 'imagery'
  sourceNameRef.value = ''
  sourceUriRef.value = ''
  sourceVersionRef.value = ''
  checksumRef.value = ''
  crsRef.value = 'EPSG:4326'
  bboxTextRef.value = ''
  securityRef.value = 'internal'
  dataStatusRef.value = 'operational'
  parentCodesRef.value = []
}

const openModal = (): void => {
  if (!props.canManage) {
    message.warning('当前项目身份无权登记多源数据资产')
    return
  }
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

const submit = (): void => {
  if (!props.operatorCode) {
    message.warning('当前项目身份尚未初始化')
    return
  }
  if (
    !assetCodeRef.value.trim()
    || !assetNameRef.value.trim()
    || !sourceNameRef.value.trim()
    || !sourceUriRef.value.trim()
    || !sourceVersionRef.value.trim()
  ) {
    message.warning('请完整填写资产编号、名称和来源信息')
    return
  }
  if (!/^[a-fA-F0-9]{64}$/.test(checksumRef.value.trim())) {
    message.warning('SHA256 必须是 64 位十六进制校验值')
    return
  }
  const bbox = parseBbox()
  if (bboxTextRef.value.trim() && !bbox) return
  emit('register', {
    asset_code: assetCodeRef.value.trim(),
    asset_name: assetNameRef.value.trim(),
    asset_type: assetTypeRef.value,
    source_name: sourceNameRef.value.trim(),
    source_uri: sourceUriRef.value.trim(),
    source_version: sourceVersionRef.value.trim(),
    checksum_sha256: checksumRef.value.trim().toLowerCase(),
    crs: crsRef.value.trim() || null,
    extent_bbox: bbox,
    time_start: null,
    time_end: null,
    security_classification: securityRef.value,
    data_status: dataStatusRef.value,
    parent_asset_codes: parentCodesRef.value,
    lineage_relation_type: 'derived_from',
    process_code: null,
    metadata: {},
    operator_code: props.operatorCode,
  })
}

defineExpose({
  closeAfterSaved: () => {
    modalOpenRef.value = false
    resetForm()
  },
})
</script>

<template>
  <section class="dataset-panel">
    <header class="panel-heading">
      <span>
        <DatabaseOutlined />
        <i><small>MULTI-SOURCE CATALOG</small><strong>多源生产数据目录</strong></i>
      </span>
      <a-button type="primary" :disabled="!canManage" @click="openModal">
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
      description="尚未登记多源生产数据；影像、矢量、DEM、控制资料、气象、UAV 和 IoT 数据将在这里统一保留来源与血缘"
    />
    <div v-else class="asset-grid">
      <article v-for="asset in assets" :key="asset.asset_code">
        <header>
          <span><DatabaseOutlined /><i><strong>{{ asset.asset_name }}</strong><small>{{ asset.asset_code }}</small></i></span>
          <a-tag :color="verificationColor(asset)">{{ verificationLabel(asset) }}</a-tag>
        </header>
        <div class="asset-tags">
          <a-tag>{{ assetTypeLabels[asset.asset_type] }}</a-tag>
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
        <code>{{ asset.checksum_sha256 }}</code>
        <div v-if="asset.parent_asset_codes.length" class="lineage">
          <ApartmentOutlined /> 派生自 {{ asset.parent_asset_codes.join('、') }}
        </div>
      </article>
    </div>

    <a-modal
      v-model:open="modalOpenRef"
      title="登记多源生产数据资产"
      width="720px"
      :confirm-loading="saving"
      ok-text="登记并写入审计"
      cancel-text="取消"
      @ok="submit"
    >
      <a-alert
        type="info"
        show-icon
        message="登记不等于实体核验"
        description="来源、版本和 SHA256 将进入目录并标记为待核验；系统不会把仅登记的记录冒充可用生产成果。"
      />
      <div class="asset-form">
        <label><span>资产编号</span><a-input v-model:value="assetCodeRef" placeholder="字母、数字、下划线或连字符" /></label>
        <label><span>资产名称</span><a-input v-model:value="assetNameRef" /></label>
        <label><span>数据类型</span><a-select v-model:value="assetTypeRef"><a-select-option v-for="option in assetTypeOptions" :key="option[0]" :value="option[0]">{{ option[1] }}</a-select-option></a-select></label>
        <label><span>来源名称</span><a-input v-model:value="sourceNameRef" placeholder="公开机构、业务系统或设备来源" /></label>
        <label class="wide"><span>来源地址</span><a-input v-model:value="sourceUriRef" placeholder="公开 URL、服务地址或受控存储 URI" /></label>
        <label><span>来源版本</span><a-input v-model:value="sourceVersionRef" placeholder="发布日期、版本号或批次" /></label>
        <label><span>数据坐标系</span><a-input v-model:value="crsRef" placeholder="如 EPSG:4326 / EPSG:4490" /></label>
        <label class="wide"><span>SHA256</span><a-input v-model:value="checksumRef" placeholder="64 位内容校验值" /></label>
        <label class="wide"><span>WGS84 范围</span><a-input v-model:value="bboxTextRef" placeholder="可选：minLon,minLat,maxLon,maxLat" /></label>
        <label><span>数据密级</span><a-select v-model:value="securityRef"><a-select-option value="public">公开</a-select-option><a-select-option value="internal">内部</a-select-option><a-select-option value="restricted">受限</a-select-option><a-select-option value="confidential">涉密</a-select-option></a-select></label>
        <label><span>数据属性</span><a-select v-model:value="dataStatusRef"><a-select-option value="operational">业务数据</a-select-option><a-select-option value="demo">明确演示数据</a-select-option></a-select></label>
        <label class="wide"><span>父资产血缘</span><a-select
          v-model:value="parentCodesRef"
          mode="multiple"
          allow-clear
          placeholder="可选：选择派生来源资产"
        ><a-select-option v-for="asset in assets" :key="asset.asset_code" :value="asset.asset_code">{{ asset.asset_code }} · {{ asset.asset_name }}</a-select-option></a-select></label>
      </div>
      <div class="audit-note"><SafetyCertificateOutlined /> 当前操作人编码：{{ operatorCode || '--' }}</div>
    </a-modal>
  </section>
</template>

<style scoped>
.dataset-panel { min-height: 420px; }
.panel-heading, .panel-heading > span, .asset-grid article header, .asset-grid article header > span { display: flex; align-items: center; }
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
.asset-grid p { margin: 8px 0 4px; overflow: hidden; font-size: 8px; color: #65736c; text-overflow: ellipsis; white-space: nowrap; }
.asset-grid code { display: block; overflow: hidden; font-size: 7px; color: #718078; text-overflow: ellipsis; white-space: nowrap; }
.lineage { padding-top: 7px; margin-top: 7px; font-size: 8px; color: #397b58; border-top: 1px dashed #d9e2dc; }
.asset-form { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 14px; }
.asset-form label { display: grid; grid-template-columns: 86px minmax(0, 1fr); gap: 8px; align-items: center; font-size: 9px; }
.asset-form .wide { grid-column: 1 / -1; }
.audit-note { padding: 9px 10px; margin-top: 12px; font-size: 8px; color: #52705f; background: #f3f7f4; border-radius: 5px; }
@media (max-width: 920px) {
  .asset-grid, .asset-form { grid-template-columns: 1fr; }
  .asset-form .wide { grid-column: auto; }
  .catalog-summary { grid-template-columns: repeat(2, 1fr); }
}
</style>
