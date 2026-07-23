<script setup lang="ts">
import {
  AimOutlined,
  CloudDownloadOutlined,
  FileSearchOutlined,
  LinkOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, ref, watch } from 'vue'

import { usePublicImageryStore } from '@/store/publicImageryStore'
import type { PublicImageryCandidate } from '@/types/publicImagery'

const publicImageryStore = usePublicImageryStore()
const {
  queryRef,
  resultRef,
  selectedItemIdRef,
  selectedCandidateComputed,
  searchingRef,
  importingRef,
  errorRef,
  lastImportRef,
  canImportComputed,
} = storeToRefs(publicImageryStore)
const assetCodeRef = ref<string>('')
const assetNameRef = ref<string>('')

const completeCandidateCountComputed = computed<number>(() => (
  resultRef.value?.items.filter(item => item.fully_covers_query).length || 0
))

const formatDateTime = (value: string): string => (
  new Date(value).toLocaleString('zh-CN', { hour12: false })
)

const platformLabel = (value: string): string => (
  value.split('-').map(part => (
    part.toLowerCase() === 'landsat'
      ? 'Landsat'
      : part.toUpperCase()
  )).join('-')
)

const wrsLabel = (candidate: PublicImageryCandidate): string => (
  candidate.wrs_path !== null && candidate.wrs_row !== null
    ? `P${String(candidate.wrs_path).padStart(3, '0')} / R${String(candidate.wrs_row).padStart(3, '0')}`
    : 'WRS 未登记'
)

const createAssetDefaults = (candidate: PublicImageryCandidate): void => {
  const dateCode = candidate.acquired_at.slice(0, 10).replaceAll('-', '')
  const pathCode = candidate.wrs_path === null
    ? 'PXXX'
    : `P${String(candidate.wrs_path).padStart(3, '0')}`
  const rowCode = candidate.wrs_row === null
    ? 'RXXX'
    : `R${String(candidate.wrs_row).padStart(3, '0')}`
  assetCodeRef.value = `LS_${dateCode}_${pathCode}_${rowCode}`
  assetNameRef.value = `${candidate.acquired_at.slice(0, 10)} ${platformLabel(candidate.platform)} ${pathCode}/${rowCode} 公开历史地表反射率`
}

const runSearch = async (): Promise<void> => {
  try {
    await publicImageryStore.search()
  } catch {
    return
  }
}

const runImport = async (): Promise<void> => {
  if (!assetCodeRef.value.trim() || !assetNameRef.value.trim()) {
    message.warning('请填写资产编号和资产名称')
    return
  }
  try {
    const response = await publicImageryStore.importSelected(
      assetCodeRef.value.trim(),
      assetNameRef.value.trim(),
    )
    message.success(`已导入 ${response.asset.asset_code}，历史覆盖矩阵已刷新`)
  } catch {
    return
  }
}

watch(selectedCandidateComputed, (candidate) => {
  if (candidate) createAssetDefaults(candidate)
})
</script>

<template>
  <div class="public-archive-panel">
    <a-alert
      type="info"
      show-icon
      message="公开 Landsat Collection 2 Level-2 历史语料"
      description="检索端点、collection 和四个反射率波段由服务端固定。导入时服务端重新读取 STAC Item，临时申请 SAS，应用 Raster Extension scale/offset 后生成 Blue/Green/Red/NIR 浮点 GeoTIFF；SAS 不进入浏览器、数据库或文件标签。"
    />

    <section class="search-form">
      <header>
        <span><small>SEARCH WINDOW</small><strong>历史时相检索窗口</strong></span>
        <a-button size="small" @click="publicImageryStore.resetBboxFromCurrentView">
          <AimOutlined /> 按当前地图中心
        </a-button>
      </header>
      <div class="form-grid date-grid">
        <label>
          <span>开始日期</span>
          <input v-model="queryRef.start_date" type="date">
        </label>
        <label>
          <span>结束日期</span>
          <input v-model="queryRef.end_date" type="date">
        </label>
        <label>
          <span>最大云量</span>
          <a-input-number
            v-model:value="queryRef.max_cloud_cover"
            :min="0"
            :max="100"
            :precision="1"
            addon-after="%"
          />
        </label>
      </div>
      <div class="bbox-grid">
        <label v-for="(label, index) in ['左经度', '下纬度', '右经度', '上纬度']" :key="label">
          <span>{{ label }}</span>
          <input v-model.number="queryRef.bbox[index]" type="number" step="0.000001">
        </label>
      </div>
      <footer>
        <span>单次范围经纬方向均不超过 3°，时间跨度不超过 10 年；导入像元上限由后端控制。</span>
        <a-button type="primary" :loading="searchingRef" @click="runSearch">
          <FileSearchOutlined /> 检索真实候选
        </a-button>
      </footer>
    </section>

    <a-alert
      v-if="errorRef"
      type="error"
      show-icon
      :message="errorRef"
    />

    <section v-if="resultRef" class="search-result">
      <header>
        <span>
          <small>SEARCH RESULT</small>
          <strong>{{ resultRef.total }} 景候选 · {{ completeCandidateCountComputed }} 景完整覆盖</strong>
        </span>
        <span class="source-ledger">
          {{ resultRef.provider }} · {{ resultRef.collection }}
        </span>
      </header>
      <a-empty
        v-if="!resultRef.items.length"
        description="当前日期、云量和空间范围没有具备完整四波段标度的 Landsat 候选"
      />
      <div v-else class="candidate-list">
        <article
          v-for="candidate in resultRef.items"
          :key="candidate.item_id"
          :class="{
            selected: selectedItemIdRef === candidate.item_id,
            partial: !candidate.fully_covers_query,
          }"
          @click="selectedItemIdRef = candidate.item_id"
        >
          <header>
            <span>
              <input
                v-model="selectedItemIdRef"
                type="radio"
                :value="candidate.item_id"
                :disabled="!candidate.fully_covers_query"
                @click.stop
              >
              <strong>{{ platformLabel(candidate.platform) }} · {{ candidate.acquired_at.slice(0, 10) }}</strong>
            </span>
            <a-tag :color="candidate.fully_covers_query ? 'green' : 'orange'">
              {{ candidate.fully_covers_query ? '完整覆盖裁取范围' : '仅相交，不可导入' }}
            </a-tag>
          </header>
          <p>{{ candidate.item_id }}</p>
          <div class="candidate-meta">
            <span>云量 {{ candidate.cloud_cover === null ? '--' : `${candidate.cloud_cover.toFixed(1)}%` }}</span>
            <span>{{ candidate.resolution_m }} m</span>
            <span>{{ candidate.processing_level }} · {{ candidate.collection_category || '未分级' }}</span>
            <span>{{ wrsLabel(candidate) }}</span>
          </div>
          <footer>
            <time>{{ formatDateTime(candidate.acquired_at) }}</time>
            <a
              :href="candidate.stac_item_url"
              target="_blank"
              rel="noreferrer"
              @click.stop
            >
              <LinkOutlined /> 查看公开 STAC Item
            </a>
          </footer>
        </article>
      </div>
    </section>

    <section v-if="selectedCandidateComputed?.fully_covers_query" class="import-form">
      <header>
        <span><small>ATOMIC INGESTION</small><strong>实体裁取与原子入库</strong></span>
        <a-tag :color="canImportComputed ? 'green' : 'red'">
          {{ canImportComputed ? '具备影像管理权限' : '当前身份无导入权限' }}
        </a-tag>
      </header>
      <div class="form-grid asset-grid">
        <label>
          <span>资产编号</span>
          <a-input v-model:value="assetCodeRef" :maxlength="80" />
        </label>
        <label>
          <span>资产名称</span>
          <a-input v-model:value="assetNameRef" :maxlength="200" />
        </label>
      </div>
      <a-alert
        type="warning"
        show-icon
        :message="resultRef?.non_statutory_notice"
        :description="`${resultRef?.license_name}。公开来源会写入实体标签和入库审计，但不会被描述为涉密、法定或已经验收的成果。`"
      />
      <footer>
        <span>服务端将重新校验 Item、四波段网格、标度、像元上限、输出实体和 SHA-256。</span>
        <a-button
          type="primary"
          :disabled="!canImportComputed"
          :loading="importingRef"
          @click="runImport"
        >
          <CloudDownloadOutlined /> 裁取并入库
        </a-button>
      </footer>
    </section>

    <a-alert
      v-if="lastImportRef"
      type="success"
      show-icon
      :message="`已入库 ${lastImportRef.asset.asset_code}`"
      :description="`源产品 ${lastImportRef.source_product_id} · ${lastImportRef.asset.file_size_bytes || 0} bytes · SHA-256 ${lastImportRef.asset.checksum_sha256}`"
    >
      <template #icon><SafetyCertificateOutlined /></template>
    </a-alert>
  </div>
</template>

<style scoped>
.public-archive-panel { display: grid; gap: 12px; }
.search-form, .search-result, .import-form { padding: 13px; border: 1px solid #e0e7e3; border-radius: 7px; background: #fbfcfb; }
.search-form > header, .search-result > header, .import-form > header, .search-form > footer, .import-form > footer { display: flex; gap: 12px; align-items: center; justify-content: space-between; }
.search-form header span, .search-result header > span:first-child, .import-form header span { display: flex; flex-direction: column; }
.search-form small, .search-result small, .import-form small { font-size: 9px; color: #839087; letter-spacing: .08em; }
.search-form strong, .search-result strong, .import-form strong { font-size: 12px; color: #304d3d; }
.form-grid, .bbox-grid { display: grid; gap: 10px; margin-top: 12px; }
.date-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.bbox-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.asset-grid { grid-template-columns: minmax(220px, .7fr) minmax(320px, 1.3fr); margin-bottom: 12px; }
label { display: grid; gap: 5px; }
label span { font-size: 10px; color: #63736a; }
label > input { box-sizing: border-box; width: 100%; height: 32px; padding: 4px 10px; color: #31483b; background: #fff; border: 1px solid #d9d9d9; border-radius: 6px; outline: none; }
label > input:focus { border-color: #4c8b68; box-shadow: 0 0 0 2px rgb(59 130 88 / 10%); }
.search-form > footer, .import-form > footer { margin-top: 12px; }
.search-form > footer span, .import-form > footer span, .source-ledger { font-size: 9px; color: #7c8982; }
.candidate-list { display: grid; max-height: 390px; gap: 8px; margin-top: 10px; overflow: auto; }
.candidate-list article { padding: 10px 12px; cursor: pointer; background: #fff; border: 1px solid #e1e7e4; border-radius: 7px; transition: border-color .15s, background .15s; }
.candidate-list article.selected { background: #f1f8f4; border-color: #569574; }
.candidate-list article.partial { cursor: default; opacity: .72; }
.candidate-list article header, .candidate-list article footer { display: flex; align-items: center; justify-content: space-between; }
.candidate-list article header span { display: flex; gap: 8px; align-items: center; }
.candidate-list article p { margin: 6px 0; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 10px; color: #51645a; }
.candidate-meta { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px; }
.candidate-meta span { padding: 5px 7px; font-size: 9px; color: #65766d; background: #f5f8f6; border-radius: 4px; }
.candidate-list footer { margin-top: 7px; font-size: 9px; color: #829087; }
.candidate-list footer a { color: #347352; }
@media (max-width: 900px) {
  .date-grid, .bbox-grid, .candidate-meta, .asset-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .search-form > footer, .import-form > footer { align-items: stretch; flex-direction: column; }
}
</style>
