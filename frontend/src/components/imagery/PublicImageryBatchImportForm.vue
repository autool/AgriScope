<script setup lang="ts">
import {
  CloudDownloadOutlined,
  DeleteOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'

import { usePublicImageryStore } from '@/store/publicImageryStore'

const publicImageryStore = usePublicImageryStore()
const {
  resultRef,
  selectedCandidatesComputed,
  selectedCoverageRatioComputed,
  assetDraftsRef,
  batchCodeRef,
  batchCommentRef,
  importingRef,
  lastImportRef,
  canImportComputed,
  validationMessagesComputed,
  canSubmitBatchComputed,
} = storeToRefs(publicImageryStore)

const removeCandidate = (itemId: string): void => {
  try {
    publicImageryStore.toggleCandidate(itemId)
  } catch (error) {
    message.warning(error instanceof Error ? error.message : '无法移除当前候选')
  }
}

const runImport = async (): Promise<void> => {
  try {
    const response = await publicImageryStore.importSelectedBatch()
    message.success(
      `批次 ${response.batch.batch_code} 已按真实足迹 ${(response.union_coverage_ratio * 100).toFixed(2)}% 联合覆盖原子入库 ${response.batch.item_count} 景`,
    )
    if (response.batch.quality_recheck_required) {
      message.warning(
        `最新业务影像已更新，已重开 ${response.batch.invalidated_task_count} 个任务的质量门禁`,
      )
    }
  } catch {
    return
  }
}
</script>

<template>
  <section class="import-form">
    <header>
      <span>
        <small>ATOMIC BATCH INGESTION</small>
        <strong>公开历史语料原子批次</strong>
      </span>
      <a-tag :color="canImportComputed ? 'green' : 'red'">
        {{ canImportComputed ? '具备影像管理权限' : '当前身份无导入权限' }}
      </a-tag>
    </header>

    <a-empty
      v-if="!selectedCandidatesComputed.length"
      :image="null"
      description="勾选一景完整覆盖，或选择 2–10 景跨轨候选联合覆盖后，可维护逐景资产清单"
    />

    <template v-else>
      <div class="batch-fields">
        <label>
          <span>批次编号</span>
          <a-input
            v-model:value="batchCodeRef"
            :maxlength="90"
            :disabled="importingRef"
          />
        </label>
        <label>
          <span>入库依据</span>
          <a-textarea
            v-model:value="batchCommentRef"
            :maxlength="500"
            :rows="2"
            :disabled="importingRef"
            placeholder="至少 10 个字符，说明历史时相用途和选择依据"
          />
        </label>
      </div>

      <div class="selected-ledger">
        <article
          v-for="candidate in selectedCandidatesComputed"
          :key="candidate.item_id"
        >
          <header>
            <span>
              <strong>{{ candidate.acquired_at.slice(0, 10) }}</strong>
              <small>{{ candidate.item_id }}</small>
            </span>
            <a-button
              type="text"
              danger
              size="small"
              :disabled="importingRef"
              @click="removeCandidate(candidate.item_id)"
            >
              <DeleteOutlined /> 移除
            </a-button>
          </header>
          <div class="asset-fields">
            <label>
              <span>资产编号</span>
              <a-input
                v-model:value="assetDraftsRef[candidate.item_id].asset_code"
                :maxlength="80"
                :disabled="importingRef"
              />
            </label>
            <label>
              <span>资产名称</span>
              <a-input
                v-model:value="assetDraftsRef[candidate.item_id].asset_name"
                :maxlength="200"
                :disabled="importingRef"
              />
            </label>
          </div>
        </article>
      </div>

      <a-alert
        type="warning"
        show-icon
        :message="resultRef?.non_statutory_notice"
        :description="`${resultRef?.license_name}。当前 bbox 联合覆盖预估 ${(selectedCoverageRatioComputed * 100).toFixed(2)}%；服务端会以真实 STAC Polygon 足迹重新执行 PostGIS 联合覆盖校验，再完成临时签名、逐景交集裁取和一次数据库事务发布；任一景失败时整批不入库。`"
      />

      <a-alert
        v-if="validationMessagesComputed.length"
        type="error"
        show-icon
        :message="validationMessagesComputed[0]"
      />

      <footer>
        <span>
          已选择 {{ selectedCandidatesComputed.length }}/{{ publicImageryStore.maxSelectedItems }} 景；
          bbox 联合覆盖约 {{ (selectedCoverageRatioComputed * 100).toFixed(2) }}%；浏览器不会接收或保存 COG/SAS URL。
        </span>
        <a-button
          type="primary"
          :disabled="!canSubmitBatchComputed"
          :loading="importingRef"
          @click="runImport"
        >
          <CloudDownloadOutlined />
          原子裁取并入库 {{ selectedCandidatesComputed.length }} 景
        </a-button>
      </footer>
    </template>

    <a-alert
      v-if="lastImportRef"
      :type="lastImportRef.batch.quality_recheck_required ? 'warning' : 'success'"
      show-icon
      :message="`批次 ${lastImportRef.batch.batch_code} 已入库 ${lastImportRef.batch.item_count} 景`"
      :description="lastImportRef.batch.quality_recheck_required
        ? `真实 STAC 足迹联合覆盖 ${(lastImportRef.union_coverage_ratio * 100).toFixed(2)}%；质量判定影像由 ${lastImportRef.batch.previous_quality_imagery_code || '无'} 切换为 ${lastImportRef.batch.current_quality_imagery_code || '--'}，已重开 ${lastImportRef.batch.invalidated_task_count} 个任务；请重新运行全量质检。`
        : `真实 STAC 足迹联合覆盖 ${(lastImportRef.union_coverage_ratio * 100).toFixed(2)}% · 清单 SHA-256 ${lastImportRef.batch.manifest_sha256} · ${lastImportRef.batch.total_size_bytes} bytes`"
    >
      <template #icon><SafetyCertificateOutlined /></template>
    </a-alert>

    <div v-if="lastImportRef" class="success-ledger">
      <span
        v-for="asset in lastImportRef.batch.items"
        :key="asset.asset_code"
      >
        <strong>{{ asset.asset_code }}</strong>
        <small>{{ asset.acquired_at.slice(0, 10) }} · {{ asset.checksum_sha256 }}</small>
      </span>
    </div>
  </section>
</template>

<style scoped>
.import-form { display: grid; gap: 12px; padding: 13px; border: 1px solid #e0e7e3; border-radius: 7px; background: #fbfcfb; }
.import-form > header, .import-form > footer, .selected-ledger article > header { display: flex; gap: 12px; align-items: center; justify-content: space-between; }
.import-form > header > span, .selected-ledger article > header > span, .success-ledger > span { display: flex; flex-direction: column; }
.import-form small { font-size: 9px; color: #839087; letter-spacing: .04em; }
.import-form strong { font-size: 12px; color: #304d3d; }
.batch-fields { display: grid; grid-template-columns: minmax(220px, .7fr) minmax(360px, 1.3fr); gap: 10px; }
label { display: grid; gap: 5px; }
label > span { font-size: 10px; color: #63736a; }
.selected-ledger { display: grid; gap: 8px; }
.selected-ledger article { padding: 10px; background: #fff; border: 1px solid #e1e7e4; border-radius: 7px; }
.asset-fields { display: grid; grid-template-columns: minmax(220px, .75fr) minmax(320px, 1.25fr); gap: 10px; margin-top: 9px; }
.import-form > footer > span { font-size: 9px; color: #7c8982; }
.success-ledger { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }
.success-ledger > span { min-width: 0; padding: 7px 9px; background: #eef7f1; border: 1px solid #d7eadc; border-radius: 5px; }
.success-ledger small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 900px) {
  .batch-fields, .asset-fields, .success-ledger { grid-template-columns: 1fr; }
  .import-form > footer { align-items: stretch; flex-direction: column; }
}
</style>
