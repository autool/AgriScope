<script setup lang="ts">
import {
  DownloadOutlined,
  FilePdfOutlined,
  PictureOutlined,
} from '@ant-design/icons-vue'

import { useThematicMapStore } from '@/store/thematicMapStore'
import type { ThematicMapProduct } from '@/types/thematicMap'

defineProps<{
  products: ThematicMapProduct[]
}>()

const thematicMapStore = useThematicMapStore()
const labels = {
  true_color: '真彩色',
  false_color: '标准假彩色',
  ndvi: 'NDVI',
}
</script>

<template>
  <section class="product-section">
    <header>
      <span><small>PHYSICAL MAP PRODUCTS</small><strong>实体专题图成果</strong></span>
      <a-tag>{{ products.length }} 张</a-tag>
    </header>
    <div v-if="products.length" class="product-grid">
      <article v-for="product in products" :key="product.product_code">
        <div class="preview">
          <img
            v-if="product.output_format === 'png' && thematicMapStore.canViewComputed"
            :src="thematicMapStore.productUrl(product, 'inline') || undefined"
            :alt="product.map_name"
          >
          <FilePdfOutlined v-else-if="product.output_format === 'pdf'" />
          <PictureOutlined v-else />
          <a-tag :color="product.status === 'completed' ? 'green' : 'error'">
            {{ product.status === 'completed' ? '实体已校验' : '实体失效' }}
          </a-tag>
        </div>
        <div class="details">
          <span><strong>{{ product.map_name }}</strong><small>{{ labels[product.source_product_code] }} · {{ product.output_format.toUpperCase() }}</small></span>
          <dl>
            <div><dt>图号</dt><dd>{{ product.map_number }}</dd></div>
            <div><dt>图幅</dt><dd>{{ product.page_width_px }}×{{ product.page_height_px }} · {{ product.dpi }} DPI</dd></div>
            <div><dt>成图 SHA</dt><dd>{{ product.checksum_sha256.slice(0, 16) }}…</dd></div>
            <div><dt>来源 SHA</dt><dd>{{ product.source_checksum_sha256.slice(0, 16) }}…</dd></div>
          </dl>
          <a-button
            size="small"
            :disabled="!thematicMapStore.canDownloadComputed || product.status !== 'completed'"
            :href="thematicMapStore.productUrl(product, 'attachment') || undefined"
          >
            <DownloadOutlined /> 下载实体成果
          </a-button>
        </div>
      </article>
    </div>
    <a-empty v-else description="尚未生成专题图实体成果" />
  </section>
</template>

<style scoped>
.product-section { min-height: 0; padding: 14px; overflow: auto; background: #fff; border: 1px solid #dfe5e2; border-radius: 8px; }
header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
header span { display: flex; flex-direction: column; }
header small { font-size: 8px; color: #87948d; }
header strong { font-size: 13px; }
.product-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr)); gap: 12px; }
article { display: grid; grid-template-columns: 150px minmax(0, 1fr); min-height: 170px; overflow: hidden; border: 1px solid #e0e6e3; border-radius: 8px; }
.preview { position: relative; display: grid; min-height: 170px; overflow: hidden; font-size: 42px; color: #708078; background: #e9efec; place-items: center; }
.preview img { width: 100%; height: 100%; object-fit: cover; }
.preview :deep(.ant-tag) { position: absolute; top: 8px; left: 8px; }
.details { display: flex; min-width: 0; flex-direction: column; gap: 8px; padding: 12px; }
.details > span { display: flex; min-width: 0; flex-direction: column; }
.details strong { overflow: hidden; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.details small { font-size: 8px; color: #7f8c85; }
dl { display: grid; gap: 4px; margin: 0; }
dl div { display: grid; grid-template-columns: 58px minmax(0, 1fr); font-size: 8px; }
dt { color: #89958f; }
dd { overflow: hidden; margin: 0; color: #405148; text-overflow: ellipsis; white-space: nowrap; }
.details :deep(.ant-btn) { align-self: flex-start; margin-top: auto; }
</style>
