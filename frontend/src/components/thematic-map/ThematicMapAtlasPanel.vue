<script setup lang="ts">
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  BookOutlined,
  DownloadOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { computed, reactive, ref, watch } from 'vue'

import { useThematicMapStore } from '@/store/thematicMapStore'
import type {
  ThematicMapAtlas,
  ThematicMapAtlasGeneratePayload,
  ThematicMapProduct,
} from '@/types/thematicMap'

const props = defineProps<{
  products: ThematicMapProduct[]
  atlases: ThematicMapAtlas[]
  disabled: boolean
  loading: boolean
}>()

const emit = defineEmits<{
  generate: [payload: Omit<ThematicMapAtlasGeneratePayload, 'operator_code'>]
}>()

const thematicMapStore = useThematicMapStore()
const orderedCodesRef = ref<string[]>([])
const form = reactive({
  atlasName: '黑龙江省农作物遥感监测专题图集',
  atlasNumber: `HLJ-RS-ATLAS-${new Date().getFullYear()}`,
  comment: '汇编当前任务全部已校验 PNG 专题图，形成封面、目录和成员校验清单',
})

const eligibleProductsComputed = computed<ThematicMapProduct[]>(() => (
  props.products
    .filter((item) => item.status === 'completed' && item.output_format === 'png')
    .sort((left, right) => (
      left.map_date.localeCompare(right.map_date)
      || left.map_number.localeCompare(right.map_number)
    ))
))

const orderedProductsComputed = computed<ThematicMapProduct[]>(() => {
  const byCode = new Map(
    eligibleProductsComputed.value.map((item) => [item.product_code, item]),
  )
  return orderedCodesRef.value
    .map((code) => byCode.get(code))
    .filter((item): item is ThematicMapProduct => Boolean(item))
})

const currentAtlasComputed = computed<ThematicMapAtlas | null>(() => (
  props.atlases.find((item) => item.is_current) || null
))

watch(
  eligibleProductsComputed,
  (products) => {
    const current = new Set(orderedCodesRef.value)
    const next = new Set(products.map((item) => item.product_code))
    if (
      current.size === next.size
      && [...current].every((code) => next.has(code))
    ) return
    orderedCodesRef.value = products.map((item) => item.product_code)
  },
  { immediate: true },
)

const move = (index: number, direction: -1 | 1): void => {
  const target = index + direction
  if (target < 0 || target >= orderedCodesRef.value.length) return
  const next = [...orderedCodesRef.value]
  const [item] = next.splice(index, 1)
  if (!item) return
  next.splice(target, 0, item)
  orderedCodesRef.value = next
}

const submit = (): void => {
  if (orderedCodesRef.value.length < 2) {
    message.warning('至少需要两张通过实体校验的 PNG 专题图')
    return
  }
  if (!form.atlasName.trim() || !form.atlasNumber.trim()) {
    message.warning('请填写图集名称和图集编号')
    return
  }
  if (form.comment.trim().length < 10) {
    message.warning('图集编排说明至少填写 10 个字符')
    return
  }
  emit('generate', {
    atlas_name: form.atlasName.trim(),
    atlas_number: form.atlasNumber.trim(),
    product_codes: [...orderedCodesRef.value],
    comment: form.comment.trim(),
  })
}
</script>

<template>
  <section class="atlas-panel">
    <header>
      <span><small>ATLAS ASSEMBLY</small><strong>任务专题图集编排</strong></span>
      <div>
        <a-tag color="green">{{ eligibleProductsComputed.length }} 张有效 PNG</a-tag>
        <a-tag>{{ atlases.length }} 个版本</a-tag>
      </div>
    </header>

    <div class="atlas-grid">
      <div class="composer">
        <a-alert
          type="info"
          show-icon
          message="图集必须覆盖当前全部有效 PNG 专题图"
          description="拖动顺序通过上下按钮完成。服务端生成封面、分页目录和统一图幅 PDF，ZIP 同时保存原始 PNG、manifest 与逐成员 SHA-256；新增或损坏专题图会使旧图集失效。"
        />
        <div v-if="orderedProductsComputed.length" class="page-order">
          <article
            v-for="(product, index) in orderedProductsComputed"
            :key="product.product_code"
          >
            <b>{{ String(index + 1).padStart(2, '0') }}</b>
            <span>
              <strong>{{ product.map_name }}</strong>
              <small>{{ product.map_number }} · {{ product.map_date }} · {{ product.checksum_sha256.slice(0, 12) }}…</small>
            </span>
            <a-button size="small" :disabled="index === 0" @click="move(index, -1)">
              <ArrowUpOutlined />
            </a-button>
            <a-button size="small" :disabled="index === orderedProductsComputed.length - 1" @click="move(index, 1)">
              <ArrowDownOutlined />
            </a-button>
          </article>
        </div>
        <a-empty v-else :image="false" description="至少生成两张有效 PNG 专题图后才能编排图集" />
        <div class="atlas-form">
          <label><span>图集名称</span><a-input v-model:value="form.atlasName" /></label>
          <label><span>图集编号</span><a-input v-model:value="form.atlasNumber" /></label>
          <label class="wide"><span>编排说明</span><a-textarea v-model:value="form.comment" :rows="2" /></label>
        </div>
        <a-button
          type="primary"
          :disabled="disabled || orderedProductsComputed.length < 2"
          :loading="loading"
          @click="submit"
        >
          <BookOutlined /> 生成 {{ orderedProductsComputed.length }} 页专题图实体图集
        </a-button>
      </div>

      <div class="atlas-history">
        <div v-if="currentAtlasComputed" class="current-atlas">
          <BookOutlined />
          <span>
            <small>CURRENT ATLAS · V{{ currentAtlasComputed.version }}</small>
            <strong>{{ currentAtlasComputed.atlas_name }}</strong>
            <em>{{ currentAtlasComputed.member_count }} 张图 · {{ currentAtlasComputed.pdf_page_count }} 页 PDF · {{ (currentAtlasComputed.package_size_bytes / 1024 / 1024).toFixed(2) }} MB</em>
          </span>
          <a-button
            type="primary"
            :disabled="!thematicMapStore.canDownloadComputed"
            :href="thematicMapStore.atlasUrl(currentAtlasComputed) || undefined"
          >
            <DownloadOutlined /> 下载 ZIP
          </a-button>
        </div>
        <a-empty v-else :image="false" description="尚未生成当前专题图集" />

        <div v-if="atlases.length" class="history-list">
          <article v-for="atlas in atlases" :key="atlas.atlas_code">
            <span>
              <strong>V{{ atlas.version }} · {{ atlas.atlas_number }}</strong>
              <small>{{ atlas.generated_at.slice(0, 16).replace('T', ' ') }} · {{ atlas.member_count }} 张 · {{ atlas.package_checksum_sha256.slice(0, 12) }}…</small>
            </span>
            <a-tag :color="atlas.is_current ? 'green' : atlas.status === 'superseded' ? 'default' : 'error'">
              {{ atlas.is_current ? '当前可交付' : atlas.status === 'superseded' ? '历史版本' : '已失效' }}
            </a-tag>
            <p v-if="atlas.stale_reason">{{ atlas.stale_reason }}</p>
          </article>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.atlas-panel { padding: 14px; background: #fff; border: 1px solid #dfe5e2; border-radius: 8px; }
header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
header > span { display: flex; flex-direction: column; }
header small { font-size: 9px; color: #87948d; }
header strong { font-size: 14px; color: #263d32; }
.atlas-grid { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(330px, 0.65fr); gap: 14px; }
.composer { display: flex; min-width: 0; flex-direction: column; gap: 10px; }
.page-order { display: grid; max-height: 190px; gap: 5px; padding-right: 4px; overflow: auto; }
.page-order article { display: grid; grid-template-columns: 34px minmax(0, 1fr) 30px 30px; gap: 6px; align-items: center; padding: 7px 8px; background: #f5f8f6; border: 1px solid #e1e7e4; border-radius: 6px; }
.page-order b { color: #3d855e; }
.page-order span { display: flex; min-width: 0; flex-direction: column; }
.page-order strong, .page-order small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.page-order strong { font-size: 10px; color: #33473d; }
.page-order small { font-size: 9px; color: #7b8982; }
.atlas-form { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.atlas-form label { display: grid; gap: 4px; font-size: 9px; color: #67766e; }
.atlas-form .wide { grid-column: 1 / -1; }
.atlas-history { min-width: 0; padding-left: 14px; border-left: 1px solid #e2e8e5; }
.current-atlas { display: grid; grid-template-columns: 34px minmax(0, 1fr) auto; gap: 9px; align-items: center; padding: 12px; color: #347a57; background: #eef7f1; border: 1px solid #cfe4d7; border-radius: 7px; }
.current-atlas > :first-child { font-size: 26px; }
.current-atlas span { display: flex; min-width: 0; flex-direction: column; }
.current-atlas small, .current-atlas em { font-size: 9px; font-style: normal; color: #71847a; }
.current-atlas strong { overflow: hidden; font-size: 11px; color: #2d503e; text-overflow: ellipsis; white-space: nowrap; }
.history-list { display: grid; max-height: 165px; gap: 6px; margin-top: 10px; overflow: auto; }
.history-list article { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 4px 8px; padding: 8px; border: 1px solid #e1e7e4; border-radius: 6px; }
.history-list span { display: flex; min-width: 0; flex-direction: column; }
.history-list strong { font-size: 10px; color: #3e5147; }
.history-list small, .history-list p { margin: 0; font-size: 9px; color: #7d8b84; }
.history-list p { grid-column: 1 / -1; color: #b26b23; }
@media (max-width: 1180px) {
  .atlas-grid { grid-template-columns: 1fr; }
  .atlas-history { padding-top: 12px; padding-left: 0; border-top: 1px solid #e2e8e5; border-left: 0; }
}
</style>
