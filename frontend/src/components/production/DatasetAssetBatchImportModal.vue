<script setup lang="ts">
import {
  ApartmentOutlined,
  DeleteOutlined,
  FileAddOutlined,
  SafetyCertificateOutlined,
  UploadOutlined,
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import { computed, ref } from 'vue'

import {
  datasetAssetTypeLabels,
  datasetAssetTypeOptions,
} from '@/components/production/datasetAssetOptions'
import type {
  DatasetAsset,
  DatasetAssetBatchCreatePayload,
  DatasetAssetBatchItemPayload,
  DatasetAssetType,
  ProductionDataStatus,
  SecurityClassification,
} from '@/types/production'

interface BatchDraftItem {
  key: string
  file: File
  inferredType: DatasetAssetType
  assetCode: string
  assetName: string
  assetType: DatasetAssetType
  crs: string
  securityClassification: SecurityClassification
  dataStatus: ProductionDataStatus
  parentAssetCodes: string[]
  processCode: string
}

const props = defineProps<{
  assets: DatasetAsset[]
  saving: boolean
  operatorCode: string | null
}>()

const emit = defineEmits<{
  submit: [payload: DatasetAssetBatchCreatePayload, files: File[]]
}>()

const MAX_FILE_COUNT = 20
const MAX_BATCH_BYTES = 20 * 1024 * 1024 * 1024

const modalOpenRef = ref<boolean>(false)
const batchCodeRef = ref<string>('')
const sourceNameRef = ref<string>('')
const sourceUriRef = ref<string>('')
const sourceVersionRef = ref<string>('')
const commentRef = ref<string>('')
const draftItemsRef = ref<BatchDraftItem[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)

const totalSizeComputed = computed<number>(() => (
  draftItemsRef.value.reduce((total, item) => total + item.file.size, 0)
))

const availableParentOptionsComputed = computed<Array<[string, string]>>(() => {
  const existing = props.assets.map((asset) => [
    asset.asset_code,
    `${asset.asset_code} · ${asset.asset_name}`,
  ] as [string, string])
  const current = draftItemsRef.value.map((item) => [
    item.assetCode,
    `${item.assetCode} · 本批次`,
  ] as [string, string])
  return [...existing, ...current].filter(([code], index, rows) => (
    code && rows.findIndex(([candidate]) => candidate === code) === index
  ))
})

const formatBytes = (value: number): string => {
  if (value <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = value
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size.toFixed(index === 0 ? 0 : 2)} ${units[index]}`
}

const inferAssetType = (filename: string): DatasetAssetType => {
  const suffix = filename.toLowerCase().split('.').pop() || ''
  if (['tif', 'tiff', 'img', 'hdf'].includes(suffix)) return 'imagery'
  if (['geojson', 'gpkg', 'kml', 'shp'].includes(suffix)) return 'vector'
  if (['nc', 'grb', 'grib'].includes(suffix)) return 'weather'
  if (['jpg', 'jpeg', 'png', 'mp4'].includes(suffix)) return 'uav'
  if (['pdf', 'docx'].includes(suffix)) return 'management'
  return 'table'
}

const buildBatchCode = (): string => {
  const now = new Date()
  const stamp = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, '0'),
    String(now.getDate()).padStart(2, '0'),
    '-',
    String(now.getHours()).padStart(2, '0'),
    String(now.getMinutes()).padStart(2, '0'),
    String(now.getSeconds()).padStart(2, '0'),
  ].join('')
  return `DSBATCH-${stamp}`
}

const buildAssetCode = (filename: string, index: number): string => {
  const base = filename
    .replace(/\.[^.]+$/, '')
    .normalize('NFKD')
    .replace(/[^A-Za-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .toUpperCase()
    .slice(0, 55) || 'ASSET'
  return `DS-${base}-${String(index + 1).padStart(2, '0')}`
}

const reset = (): void => {
  batchCodeRef.value = buildBatchCode()
  sourceNameRef.value = ''
  sourceUriRef.value = ''
  sourceVersionRef.value = ''
  commentRef.value = ''
  draftItemsRef.value = []
  if (fileInputRef.value) fileInputRef.value.value = ''
}

const open = (): void => {
  reset()
  modalOpenRef.value = true
}

const closeAfterSaved = (): void => {
  modalOpenRef.value = false
  reset()
}

const requestClose = (): void => {
  if (!draftItemsRef.value.length || props.saving) {
    if (!props.saving) modalOpenRef.value = false
    return
  }
  Modal.confirm({
    title: '放弃未提交的批量清单？',
    content: `当前已选择 ${draftItemsRef.value.length} 个文件，关闭后逐文件元数据不会保留。`,
    okText: '放弃清单',
    cancelText: '继续编辑',
    okType: 'danger',
    onOk: () => {
      modalOpenRef.value = false
      reset()
    },
  })
}

const triggerFileSelect = (): void => {
  fileInputRef.value?.click()
}

const selectFiles = (event: Event): void => {
  const target = event.target as HTMLInputElement
  const selected = Array.from(target.files || [])
  if (!selected.length) return
  if (selected.length > MAX_FILE_COUNT) {
    message.warning(`单批最多选择 ${MAX_FILE_COUNT} 个文件`)
    target.value = ''
    return
  }
  const normalizedNames = selected.map((file) => file.name.toLocaleLowerCase())
  if (new Set(normalizedNames).size !== normalizedNames.length) {
    message.warning('同一批次不能包含重名文件（忽略大小写）')
    target.value = ''
    return
  }
  const totalSize = selected.reduce((total, file) => total + file.size, 0)
  if (totalSize > MAX_BATCH_BYTES) {
    message.warning('批次总大小不能超过 20 GB')
    target.value = ''
    return
  }
  draftItemsRef.value = selected.map((file, index) => {
    const inferredType = inferAssetType(file.name)
    return {
      key: `${file.name}-${file.size}-${file.lastModified}-${index}`,
      file,
      inferredType,
      assetCode: buildAssetCode(file.name, index),
      assetName: file.name.replace(/\.[^.]+$/, ''),
      assetType: inferredType,
      crs: '',
      securityClassification: 'public',
      dataStatus: 'operational',
      parentAssetCodes: [],
      processCode: '',
    }
  })
}

const removeItem = (key: string): void => {
  draftItemsRef.value = draftItemsRef.value.filter((item) => item.key !== key)
}

const hasLineageCycle = (): boolean => {
  const batchCodes = new Set(draftItemsRef.value.map((item) => item.assetCode))
  const graph = new Map(
    draftItemsRef.value.map((item) => [
      item.assetCode,
      item.parentAssetCodes.filter((code) => batchCodes.has(code)),
    ]),
  )
  const visiting = new Set<string>()
  const visited = new Set<string>()
  const visit = (code: string): boolean => {
    if (visiting.has(code)) return true
    if (visited.has(code)) return false
    visiting.add(code)
    for (const parent of graph.get(code) || []) {
      if (visit(parent)) return true
    }
    visiting.delete(code)
    visited.add(code)
    return false
  }
  return [...graph.keys()].some((code) => visit(code))
}

const buildPayload = (): DatasetAssetBatchCreatePayload | null => {
  const operatorCode = props.operatorCode
  if (!operatorCode) {
    message.warning('当前项目身份尚未初始化')
    return null
  }
  const batchCode = batchCodeRef.value.trim()
  if (!/^[A-Za-z0-9_-]{1,90}$/.test(batchCode)) {
    message.warning('批次编号只能包含字母、数字、下划线或连字符')
    return null
  }
  if (!draftItemsRef.value.length || draftItemsRef.value.length > MAX_FILE_COUNT) {
    message.warning(`请选择 1–${MAX_FILE_COUNT} 个需要原子入库的实体文件`)
    return null
  }
  const sourceName = sourceNameRef.value.trim()
  const sourceUri = sourceUriRef.value.trim()
  const sourceVersion = sourceVersionRef.value.trim()
  if (!sourceName || !sourceUri || !sourceVersion) {
    message.warning('请完整填写本批次共同来源名称、地址和版本')
    return null
  }
  const comment = commentRef.value.trim()
  if (comment.length < 10) {
    message.warning('批量入库依据至少填写 10 个字符')
    return null
  }
  const assetCodes = draftItemsRef.value.map((item) => item.assetCode.trim())
  if (assetCodes.some((code) => !/^[A-Za-z0-9_-]{1,80}$/.test(code))) {
    message.warning('逐文件资产编号只能包含字母、数字、下划线或连字符')
    return null
  }
  if (new Set(assetCodes).size !== assetCodes.length) {
    message.warning('同一批次不得包含重复资产编号')
    return null
  }
  if (draftItemsRef.value.some((item) => !item.assetName.trim())) {
    message.warning('请完整填写每个文件的资产名称')
    return null
  }
  if (draftItemsRef.value.some((item) => (
    item.parentAssetCodes.includes(item.assetCode)
  ))) {
    message.warning('资产不能把自身设置为父资产')
    return null
  }
  if (hasLineageCycle()) {
    message.warning('本批次父资产血缘形成循环，请调整后再提交')
    return null
  }
  const items: DatasetAssetBatchItemPayload[] = draftItemsRef.value.map((item) => ({
    filename: item.file.name,
    asset_code: item.assetCode.trim(),
    asset_name: item.assetName.trim(),
    asset_type: item.assetType,
    source_name: sourceName,
    source_uri: sourceUri,
    source_version: sourceVersion,
    crs: item.crs.trim() || null,
    extent_bbox: null,
    time_start: null,
    time_end: null,
    security_classification: item.securityClassification,
    data_status: item.dataStatus,
    parent_asset_codes: item.parentAssetCodes,
    lineage_relation_type: 'derived_from',
    process_code: item.processCode.trim() || null,
    metadata: {
      browser_file_last_modified: new Date(item.file.lastModified).toISOString(),
      frontend_inferred_asset_type: item.inferredType,
    },
  }))
  return {
    batch_code: batchCode,
    operator_code: operatorCode,
    comment,
    items,
  }
}

const submit = (): void => {
  const payload = buildPayload()
  if (!payload) return
  emit('submit', payload, draftItemsRef.value.map((item) => item.file))
}

defineExpose({ open, closeAfterSaved })
</script>

<template>
  <a-modal
    :open="modalOpenRef"
    title="多源数据资产原子批量入库"
    width="1120px"
    :confirm-loading="saving"
    :mask-closable="false"
    ok-text="整批校验、发布并入库"
    cancel-text="取消"
    @ok="submit"
    @cancel="requestClose"
  >
    <a-alert
      type="info"
      show-icon
      message="一次请求、一次业务事务"
      description="平台先临时检查全部文件并计算服务端 SHA-256；任一文件、血缘、发布或数据库步骤失败，整批不入库且清理全部新实体。"
    />

    <section class="batch-header-form">
      <label><span>批次编号</span><a-input v-model:value="batchCodeRef" /></label>
      <label><span>共同来源名称</span><a-input v-model:value="sourceNameRef" placeholder="公开机构、业务系统或交接单位" /></label>
      <label class="wide"><span>共同来源地址</span><a-input v-model:value="sourceUriRef" placeholder="公开 URL、交接单号或来源系统 URI" /></label>
      <label><span>来源版本</span><a-input v-model:value="sourceVersionRef" placeholder="发布日期、版本号或交接批次" /></label>
      <label><span>稳定操作人</span><a-input :value="operatorCode || '--'" disabled /></label>
      <label class="wide"><span>批量入库依据</span><a-textarea v-model:value="commentRef" :rows="2" placeholder="至少 10 个字符，说明数据来源、交接证据和本次业务用途" /></label>
    </section>

    <section class="file-selection">
      <div>
        <strong><FileAddOutlined /> 批次文件清单</strong>
        <small>选择 1–20 个文件；扩展名仅用于初始类型推断，每行均可人工修正。</small>
      </div>
      <input
        ref="fileInputRef"
        type="file"
        multiple
        @change="selectFiles"
      >
      <a-button :disabled="saving" @click="triggerFileSelect">
        <UploadOutlined /> {{ draftItemsRef.length ? '重新选择全部文件' : '选择多个文件' }}
      </a-button>
    </section>

    <div class="batch-metrics">
      <span><strong>{{ draftItemsRef.length }} / 20</strong><small>批次成员</small></span>
      <span><strong>{{ formatBytes(totalSizeComputed) }}</strong><small>批次总大小 / 上限 20 GB</small></span>
      <span><strong>{{ new Set(draftItemsRef.map((item) => item.assetType)).size }}</strong><small>数据类型</small></span>
      <span><strong>{{ draftItemsRef.filter((item) => item.parentAssetCodes.length).length }}</strong><small>带血缘成员</small></span>
    </div>

    <a-empty
      v-if="!draftItemsRef.length"
      class="batch-empty"
      description="请选择需要作为一个不可分割批次入库的实体文件"
    />
    <div v-else class="batch-item-list">
      <article v-for="(item, index) in draftItemsRef" :key="item.key">
        <header>
          <span><strong>{{ index + 1 }}. {{ item.file.name }}</strong><small>{{ formatBytes(item.file.size) }} · 推断为 {{ datasetAssetTypeLabels[item.inferredType] }}</small></span>
          <a-button
            danger
            type="text"
            :disabled="saving"
            @click="removeItem(item.key)"
          >
            <DeleteOutlined /> 移除
          </a-button>
        </header>
        <div class="item-fields">
          <label><span>资产编号</span><a-input v-model:value="item.assetCode" /></label>
          <label><span>资产名称</span><a-input v-model:value="item.assetName" /></label>
          <label><span>数据类型</span><a-select v-model:value="item.assetType"><a-select-option v-for="option in datasetAssetTypeOptions" :key="option[0]" :value="option[0]">{{ option[1] }}</a-select-option></a-select></label>
          <label><span>坐标系</span><a-input v-model:value="item.crs" placeholder="可选，如 EPSG:4326" /></label>
          <label><span>数据密级</span><a-select v-model:value="item.securityClassification"><a-select-option value="public">公开</a-select-option><a-select-option value="internal">内部</a-select-option><a-select-option value="restricted">受限</a-select-option><a-select-option value="confidential">涉密</a-select-option></a-select></label>
          <label><span>业务属性</span><a-select v-model:value="item.dataStatus"><a-select-option value="operational">业务数据</a-select-option><a-select-option value="demo">明确演示数据</a-select-option></a-select></label>
          <label class="wide"><span>父资产血缘</span><a-select
            v-model:value="item.parentAssetCodes"
            mode="multiple"
            allow-clear
            placeholder="可选：既有资产或本批其他成员"
          ><a-select-option
            v-for="option in availableParentOptionsComputed"
            :key="option[0]"
            :value="option[0]"
            :disabled="option[0] === item.assetCode"
          >{{ option[1] }}</a-select-option></a-select></label>
          <label class="wide"><span>处理过程编号</span><a-input v-model:value="item.processCode" placeholder="可选：派生处理任务、模型或交接过程编号" /></label>
        </div>
      </article>
    </div>

    <footer class="audit-note">
      <SafetyCertificateOutlined />
      <span>服务端将保存成员顺序、实体大小、SHA-256、格式检查、稳定操作人角色及规范化 manifest SHA-256；前端不会循环调用单文件接口。</span>
      <ApartmentOutlined />
    </footer>
  </a-modal>
</template>

<style scoped>
.batch-header-form { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 14px; margin-top: 14px; }
.batch-header-form label, .item-fields label { display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: 8px; align-items: center; font-size: 9px; }
.batch-header-form label > span, .item-fields label > span { color: #4d5f55; }
.batch-header-form .wide, .item-fields .wide { grid-column: 1 / -1; }
.file-selection { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 11px 12px; margin-top: 14px; background: #f5f8f6; border: 1px solid #dfe7e2; border-radius: 7px; }
.file-selection > div { display: flex; flex-direction: column; min-width: 0; }
.file-selection strong { font-size: 11px; color: #315d45; }
.file-selection small { margin-top: 2px; font-size: 8px; color: #718078; }
.file-selection input { display: none; }
.batch-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 9px 0; }
.batch-metrics span { display: flex; flex-direction: column; padding: 8px 10px; background: #fafbfa; border: 1px solid #e3e9e5; border-radius: 6px; }
.batch-metrics strong { font-size: 13px; color: #397b58; }
.batch-metrics small { font-size: 8px; color: #7d8a83; }
.batch-empty { padding: 34px 20px; border: 1px dashed #d8e1db; border-radius: 7px; }
.batch-item-list { display: grid; gap: 8px; max-height: 410px; padding-right: 4px; overflow: auto; }
.batch-item-list article { padding: 10px; background: #fafbfa; border: 1px solid #dfe6e2; border-radius: 7px; }
.batch-item-list article > header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 9px; }
.batch-item-list article > header span { display: flex; flex-direction: column; min-width: 0; }
.batch-item-list article > header strong { overflow: hidden; font-size: 10px; color: #2f4037; text-overflow: ellipsis; white-space: nowrap; }
.batch-item-list article > header small { margin-top: 2px; font-size: 8px; color: #7a8981; }
.item-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 12px; }
.audit-note { display: flex; align-items: center; gap: 8px; padding: 9px 11px; margin-top: 12px; font-size: 8px; color: #52705f; background: #f1f7f3; border-radius: 6px; }
.audit-note span { flex: 1; }
@media (max-width: 920px) {
  .batch-header-form, .item-fields { grid-template-columns: 1fr; }
  .batch-header-form .wide, .item-fields .wide { grid-column: auto; }
  .batch-metrics { grid-template-columns: repeat(2, 1fr); }
}
</style>
