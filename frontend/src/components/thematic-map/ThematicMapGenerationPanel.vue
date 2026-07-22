<script setup lang="ts">
import { message } from 'ant-design-vue'
import { computed, reactive, watch } from 'vue'

import type {
  ThematicMapBatchGeneratePayload,
  ThematicMapSource,
  ThematicMapTemplate,
  ThematicOutputFormat,
  ThematicSourceProductCode,
} from '@/types/thematicMap'

const props = defineProps<{
  templates: ThematicMapTemplate[]
  sources: ThematicMapSource[]
  disabled: boolean
  loading: boolean
}>()

const emit = defineEmits<{
  generate: [payload: Omit<ThematicMapBatchGeneratePayload, 'operator_code'>]
}>()

const form = reactive({
  templateCode: '',
  assetCode: '',
  products: ['true_color', 'false_color', 'ndvi'] as ThematicSourceProductCode[],
  formats: ['png'] as ThematicOutputFormat[],
  mapNumberPrefix: 'HLJ-RS-2026',
  mapDate: new Date().toISOString().slice(0, 10),
  comment: '从已校验波段产品批量生成实体专题图成果',
})

const eligibleSourcesComputed = computed(() => (
  props.sources.filter((source) => source.eligible)
))
const selectedSourceComputed = computed(() => (
  eligibleSourcesComputed.value.find((source) => source.asset_code === form.assetCode)
))
const productOptions = [
  { label: '真彩色', value: 'true_color' },
  { label: '标准假彩色', value: 'false_color' },
  { label: 'NDVI', value: 'ndvi' },
]
const productLabels: Record<ThematicSourceProductCode, string> = {
  true_color: '真彩色影像专题图',
  false_color: '标准假彩色专题图',
  ndvi: 'NDVI 植被指数专题图',
}
const productCodes: Record<ThematicSourceProductCode, string> = {
  true_color: 'RGB',
  false_color: 'FCC',
  ndvi: 'NDVI',
}

watch(
  () => [props.templates, eligibleSourcesComputed.value] as const,
  () => {
    if (!form.templateCode && props.templates[0]) {
      form.templateCode = props.templates[0].template_code
    }
    if (!form.assetCode && eligibleSourcesComputed.value[0]) {
      form.assetCode = eligibleSourcesComputed.value[0].asset_code
    }
  },
  { immediate: true, deep: true },
)

const submit = (): void => {
  if (!form.templateCode || !form.assetCode) {
    message.warning('请先选择真实模板和可用影像产品')
    return
  }
  if (!form.products.length || !form.formats.length) {
    message.warning('至少选择一种专题产品和输出格式')
    return
  }
  if (!form.mapNumberPrefix.trim()) {
    message.warning('请填写图号前缀')
    return
  }
  const source = selectedSourceComputed.value
  if (!source) return
  emit('generate', {
    template_code: form.templateCode,
    asset_code: form.assetCode,
    comment: form.comment.trim(),
    items: form.products.flatMap((product) => (
      form.formats.map((format) => ({
        source_product_code: product,
        output_format: format,
        map_name: `${source.asset_name} · ${productLabels[product]}`,
        map_number: `${form.mapNumberPrefix}-${productCodes[product]}-${format.toUpperCase()}`,
        map_date: form.mapDate,
      }))
    )),
  })
}
</script>

<template>
  <section class="generation-panel">
    <header>
      <span><small>BATCH COMPOSER</small><strong>实体专题图批量生成</strong></span>
      <a-tag color="green">最多 12 张/批</a-tag>
    </header>
    <a-alert
      v-if="!eligibleSourcesComputed.length"
      type="warning"
      show-icon
      message="没有可用于正式制图的实体产品"
      description="仅 operational 且 band_products 文件、大小和 SHA-256 全部有效的影像可用。"
    />
    <div class="generation-form">
      <label><span>版式模板</span><a-select v-model:value="form.templateCode" :options="templates.map((item) => ({ value: item.template_code, label: `${item.template_name} · ${item.dpi} DPI` }))" /></label>
      <label><span>实体影像来源</span><a-select v-model:value="form.assetCode" :options="eligibleSourcesComputed.map((item) => ({ value: item.asset_code, label: `${item.asset_code} · ${item.acquired_at.slice(0, 10)}` }))" /></label>
      <label><span>专题产品</span><a-checkbox-group v-model:value="form.products" :options="productOptions" /></label>
      <label><span>输出格式</span><a-checkbox-group v-model:value="form.formats" :options="[{ label: 'PNG', value: 'png' }, { label: 'PDF', value: 'pdf' }]" /></label>
      <label><span>图号前缀</span><a-input v-model:value="form.mapNumberPrefix" /></label>
      <label><span>制图日期</span><a-input v-model:value="form.mapDate" type="date" /></label>
      <label class="wide"><span>生成说明</span><a-textarea v-model:value="form.comment" :rows="2" /></label>
    </div>
    <div v-if="selectedSourceComputed" class="source-evidence">
      <small>实体来源</small>
      <strong>{{ selectedSourceComputed.source_uri }}</strong>
      <span>SHA256 {{ selectedSourceComputed.source_checksum_sha256 }}</span>
    </div>
    <a-button
      type="primary"
      block
      :disabled="disabled || !eligibleSourcesComputed.length"
      :loading="loading"
      @click="submit"
    >
      批量生成 {{ form.products.length * form.formats.length }} 张实体专题图
    </a-button>
  </section>
</template>

<style scoped>
.generation-panel { height: 100%; padding: 14px; overflow: auto; background: #fff; border: 1px solid #dfe5e2; border-radius: 8px; }
header { display: flex; align-items: center; justify-content: space-between; }
header span { display: flex; flex-direction: column; }
header small { font-size: 8px; color: #87948d; }
header strong { font-size: 13px; }
.generation-form { display: grid; gap: 11px; margin: 16px 0; }
.generation-form label { display: grid; grid-template-columns: 90px minmax(0, 1fr); gap: 10px; align-items: center; font-size: 9px; color: #65736c; }
.source-evidence { display: flex; flex-direction: column; gap: 3px; padding: 10px; margin-bottom: 12px; overflow: hidden; background: #f3f7f5; border-radius: 6px; }
.source-evidence small { font-size: 8px; color: #829087; }
.source-evidence strong, .source-evidence span { overflow: hidden; font-size: 8px; color: #40544a; text-overflow: ellipsis; white-space: nowrap; }
</style>
