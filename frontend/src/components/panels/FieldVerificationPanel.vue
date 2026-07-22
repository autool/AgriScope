<script setup lang="ts">
import { UploadOutlined } from '@ant-design/icons-vue'
import { Empty, message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { onMounted, ref } from 'vue'

import FieldCsvImportModal from '@/components/field/FieldCsvImportModal.vue'
import { useFieldStore } from '@/store/fieldStore'
import type {
  FieldResolutionPayload,
  FieldVerificationBatchImportPayload,
  FieldVerificationFileImportMetadata,
} from '@/types/workbench'

const fieldStore = useFieldStore()
const {
  canRematchComputed,
  canResolveComputed,
  canUploadComputed,
  importingRef,
  listRef,
  loadingRef,
  selectedCodeRef,
  selectedRecordComputed,
} = storeToRefs(fieldStore)
const importModalOpenRef = ref<boolean>(false)

/**
 * 处置当前外业疑点。
 * Args:
 *   decision: 采用外业或保留内业。
 * Returns:
 *   Promise<void>: 疑点闭环完成后结束。
 */
const handleResolve = async (
  decision: FieldResolutionPayload['decision'],
): Promise<void> => {
  try {
    await fieldStore.resolveSelected(decision)
    message.success('外业疑点已完成处置并写入审核记录')
  } catch {
    // 请求拦截器已显示安全错误，避免组件事件产生未捕获 Promise。
  }
}

/**
 * 使用项目当前规则重新执行全部外业点空间匹配。
 * Args:
 *   无。
 * Returns:
 *   Promise<void>: 重新匹配和列表刷新完成后结束。
 */
const handleRematch = async (): Promise<void> => {
  try {
    await fieldStore.rematch()
    message.success('已按当前项目阈值重新匹配全部外业点')
  } catch {
    // 请求拦截器已显示安全错误，避免组件事件产生未捕获 Promise。
  }
}

/**
 * 导入外业 CSV 并显示自动匹配结果。
 * Args:
 *   payload: 已解析的来源和外业记录。
 * Returns:
 *   Promise<void>: 导入完成后关闭弹窗。
 */
const handleImport = async (
  payload: Omit<FieldVerificationBatchImportPayload, 'uploader_code'>,
): Promise<void> => {
  try {
    const result = await fieldStore.importCsv(payload)
    importModalOpenRef.value = false
    message.success(
      `批次 ${result.batch_code} 已导入 ${result.imported_count} 条，生成 ${result.issue_count} 条疑点`,
    )
  } catch {
    // 请求拦截器已显示安全错误，保留弹窗便于修正。
  }
}

/**
 * 上传外业 Excel 并显示服务端校验与匹配结果。
 * Args:
 *   file: 原始 XLSX 工作簿。
 *   metadata: 来源、版本和导入依据。
 * Returns:
 *   Promise<void>: 导入完成后关闭弹窗。
 */
const handleImportXlsx = async (
  file: File,
  metadata: Omit<FieldVerificationFileImportMetadata, 'uploader_code'>,
): Promise<void> => {
  try {
    const result = await fieldStore.importXlsx(file, metadata)
    importModalOpenRef.value = false
    message.success(
      `Excel 批次 ${result.batch_code} 已导入 ${result.imported_count} 条，生成 ${result.issue_count} 条疑点`,
    )
  } catch {
    // 请求拦截器已显示安全错误，保留弹窗便于修正。
  }
}

/**
 * 下载服务端生成的外业 Excel 标准模板。
 * Returns:
 *   Promise<void>: 浏览器下载动作触发后结束。
 */
const handleDownloadXlsxTemplate = async (): Promise<void> => {
  try {
    const { blob, filename } = await fieldStore.downloadXlsxTemplate()
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    window.URL.revokeObjectURL(url)
  } catch {
    // 请求拦截器已显示安全错误。
  }
}

onMounted(() => { void fieldStore.load() })
</script>

<template>
  <section class="panel">
    <header>
      <span><small>内外业空间校核</small><strong>外业核查点</strong></span>
      <div class="header-actions">
        <a-button
          v-if="canUploadComputed"
          type="primary"
          size="small"
          @click="importModalOpenRef = true"
        >
          <UploadOutlined />导入 CSV/Excel
        </a-button>
        <a-button
          size="small"
          :loading="loadingRef"
          :disabled="!canRematchComputed"
          title="仅质检员或项目负责人可重新匹配"
          @click="handleRematch"
        >
          重新匹配
        </a-button>
      </div>
    </header>
    <a-alert
      v-if="!canRematchComputed && !canResolveComputed && !canUploadComputed"
      class="permission-alert"
      type="info"
      show-icon
      message="当前身份为只读模式"
      description="外业重新匹配和疑点处置需要质检员或项目负责人权限。"
    />
    <div class="metrics"><div><strong>{{ listRef?.total ?? 0 }}</strong><small>核查点</small></div><div class="success"><strong>{{ listRef?.consistent ?? 0 }}</strong><small>一致</small></div><div class="warning"><strong>{{ listRef?.offset ?? 0 }}</strong><small>偏移</small></div><div class="time"><strong>{{ listRef?.time_mismatch ?? 0 }}</strong><small>时间超限</small></div><div class="danger"><strong>{{ listRef?.unmatched ?? 0 }}</strong><small>未匹配</small></div></div>
    <div class="record-list">
      <button
        v-for="item in listRef?.items || []"
        :key="item.verification_code"
        :class="{ active: selectedRecordComputed?.verification_code === item.verification_code }"
        @click="selectedCodeRef = item.verification_code"
      >
        <i :class="item.match_status" /><span><strong>{{ item.verification_code }}</strong><small>{{ item.investigator }} · {{ item.observed_land_class }}</small></span><em>{{ item.offset_distance_m ?? '--' }} m</em>
      </button>
      <a-empty
        v-if="!loadingRef && !(listRef?.items.length)"
        :image="Empty.PRESENTED_IMAGE_SIMPLE"
        description="尚未导入真实外业核查记录"
      >
        <a-button
          v-if="canUploadComputed"
          type="primary"
          size="small"
          @click="importModalOpenRef = true"
        >
          导入 CSV/Excel
        </a-button>
      </a-empty>
    </div>
    <div v-if="selectedRecordComputed" class="detail">
      <h3>{{ selectedRecordComputed.verification_code }}</h3>
      <dl><div><dt>匹配图斑</dt><dd>{{ selectedRecordComputed.matched_plot_code || '未匹配' }}</dd></div><div><dt>外业作物</dt><dd>{{ selectedRecordComputed.observed_crop_type || '--' }}</dd></div><div><dt>匹配状态</dt><dd>{{ selectedRecordComputed.match_status }}</dd></div><div><dt>处置状态</dt><dd>{{ selectedRecordComputed.resolution_status }}</dd></div></dl>
      <dl class="source-audit">
        <div><dt>采集来源</dt><dd>{{ selectedRecordComputed.source_name || '--' }}</dd></div>
        <div><dt>来源版本</dt><dd>{{ selectedRecordComputed.source_version || '--' }}</dd></div>
        <div><dt>来源记录</dt><dd>{{ selectedRecordComputed.source_record_id || '--' }}</dd></div>
        <div><dt>导入批次</dt><dd>{{ selectedRecordComputed.import_batch_code || '--' }}</dd></div>
        <div><dt>采集时间</dt><dd>{{ selectedRecordComputed.captured_at }}</dd></div>
        <div><dt>照片证据</dt><dd>{{ selectedRecordComputed.photo_urls.length }} 张</dd></div>
      </dl>
      <div v-if="selectedRecordComputed.resolution_status === 'pending'" class="actions">
        <a-button
          type="primary"
          :disabled="!canResolveComputed"
          @click="handleResolve('use_field')"
        >
          采用外业结论
        </a-button>
        <a-button
          :disabled="!canResolveComputed"
          @click="handleResolve('keep_internal')"
        >
          保留内业成果
        </a-button>
      </div>
      <a-alert
        v-else
        type="success"
        show-icon
        message="该外业记录已完成闭环"
      />
    </div>
    <FieldCsvImportModal
      :open="importModalOpenRef"
      :loading="importingRef"
      @cancel="importModalOpenRef = false"
      @submit-csv="handleImport"
      @submit-xlsx="handleImportXlsx"
      @download-xlsx-template="handleDownloadXlsxTemplate"
    />
  </section>
</template>

<style scoped>
.panel { height: 100%; padding: 12px; overflow: auto; }
header { display: flex; align-items: center; justify-content: space-between; }
header > span { display: flex; flex-direction: column; }
small { font-size: 7px; color: #8b9690; }
header strong { font-size: 12px; }
.header-actions { display: flex; gap: 5px; }
.metrics { display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; margin: 10px 0; }
.permission-alert { margin-top: 10px; }
.metrics > div { padding: 7px 2px; text-align: center; background: #f4f6f5; border-radius: 4px; }
.metrics strong, .metrics small { display: block; }
.metrics strong { font-size: 15px; }
.metrics .success strong { color: #3f9667; }
.metrics .warning strong { color: #c27a2d; }
.metrics .time strong { color: #7a63b8; }
.metrics .danger strong { color: #d55252; }
.record-list button { display: grid; grid-template-columns: 8px 1fr auto; gap: 7px; align-items: center; width: 100%; min-height: 45px; padding: 7px; text-align: left; background: #fff; border: 0; border-bottom: 1px solid #edf0ee; }
.record-list button.active { background: #f0f6f2; }
.record-list i { width: 7px; height: 7px; background: #e05252; border-radius: 50%; }
.record-list i.consistent { background: #4eb47a; }
.record-list i.offset { background: #f0a43b; }
.record-list i.time_mismatch { background: #7a63b8; }
.record-list span { display: flex; flex-direction: column; }
.record-list strong { font-size: 8px; }
.record-list em { font-size: 7px; font-style: normal; color: #8b9690; }
.detail { padding-top: 12px; margin-top: 12px; border-top: 1px solid #e6eae8; }
.detail h3 { font-size: 11px; }
.detail dl > div { display: flex; justify-content: space-between; padding: 7px 0; font-size: 8px; border-bottom: 1px dashed #e5e9e7; }
.detail dd { margin: 0; font-weight: 600; }
.source-audit { padding: 7px 8px; margin-top: 8px; background: #f7f9f8; border: 1px solid #e7ece9; border-radius: 5px; }
.source-audit dd { max-width: 185px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.actions { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 10px; }
</style>
