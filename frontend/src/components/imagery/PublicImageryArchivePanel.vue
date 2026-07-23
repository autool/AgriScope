<script setup lang="ts">
import {
  AimOutlined,
  FileSearchOutlined,
  LinkOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed } from 'vue'

import PublicImageryBatchImportForm from '@/components/imagery/PublicImageryBatchImportForm.vue'
import { usePublicImageryStore } from '@/store/publicImageryStore'
import type { PublicImageryCandidate } from '@/types/publicImagery'

const publicImageryStore = usePublicImageryStore()
const {
  queryRef,
  resultRef,
  selectedItemIdsRef,
  searchingRef,
  errorRef,
} = storeToRefs(publicImageryStore)

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

const runSearch = async (): Promise<void> => {
  try {
    await publicImageryStore.search()
  } catch {
    return
  }
}

const toggleCandidate = (itemId: string): void => {
  try {
    publicImageryStore.toggleCandidate(itemId)
  } catch (error) {
    message.warning(error instanceof Error ? error.message : '无法选择当前候选')
  }
}
</script>

<template>
  <div class="public-archive-panel">
    <a-alert
      type="info"
      show-icon
      message="公开 Landsat Collection 2 Level-2 历史语料"
      description="检索端点、collection 和四个反射率波段由服务端固定。可选择 1–10 景候选；服务端逐景重新读取 STAC Item、临时申请 SAS、应用 Raster Extension scale/offset，并在全部裁取成功后通过一次影像批次事务入库。SAS 不进入浏览器、数据库或文件标签。"
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
            selected: selectedItemIdsRef.includes(candidate.item_id),
            partial: !candidate.fully_covers_query,
          }"
          @click="candidate.fully_covers_query && toggleCandidate(candidate.item_id)"
        >
          <header>
            <span>
              <input
                type="checkbox"
                :checked="selectedItemIdsRef.includes(candidate.item_id)"
                :disabled="!candidate.fully_covers_query"
                @click.stop="toggleCandidate(candidate.item_id)"
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

    <PublicImageryBatchImportForm v-if="resultRef" />
  </div>
</template>

<style scoped>
.public-archive-panel { display: grid; gap: 12px; }
.search-form, .search-result { padding: 13px; border: 1px solid #e0e7e3; border-radius: 7px; background: #fbfcfb; }
.search-form > header, .search-result > header, .search-form > footer { display: flex; gap: 12px; align-items: center; justify-content: space-between; }
.search-form header span, .search-result header > span:first-child { display: flex; flex-direction: column; }
.search-form small, .search-result small { font-size: 9px; color: #839087; letter-spacing: .08em; }
.search-form strong, .search-result strong { font-size: 12px; color: #304d3d; }
.form-grid, .bbox-grid { display: grid; gap: 10px; margin-top: 12px; }
.date-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.bbox-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
label { display: grid; gap: 5px; }
label span { font-size: 10px; color: #63736a; }
label > input { box-sizing: border-box; width: 100%; height: 32px; padding: 4px 10px; color: #31483b; background: #fff; border: 1px solid #d9d9d9; border-radius: 6px; outline: none; }
label > input:focus { border-color: #4c8b68; box-shadow: 0 0 0 2px rgb(59 130 88 / 10%); }
.search-form > footer { margin-top: 12px; }
.search-form > footer span, .source-ledger { font-size: 9px; color: #7c8982; }
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
  .date-grid, .bbox-grid, .candidate-meta { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .search-form > footer { align-items: stretch; flex-direction: column; }
}
</style>
