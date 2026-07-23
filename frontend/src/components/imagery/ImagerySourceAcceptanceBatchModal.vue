<script setup lang="ts">
import {
  CheckCircleOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { watch } from 'vue'

import { useImagerySourceAcceptanceStore } from '@/store/imagerySourceAcceptanceStore'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  success: [message: string]
}>()

const sourceAcceptanceStore = useImagerySourceAcceptanceStore()
const {
  selectedAssetCodesRef,
  justificationRef,
  confirmationRef,
  acceptingRef,
  errorRef,
  lastResultRef,
  canProcessComputed,
  eligibleAssetsComputed,
  selectedAssetsComputed,
  validationMessagesComputed,
  canSubmitComputed,
} = storeToRefs(sourceAcceptanceStore)

const toggleAsset = (assetCode: string): void => {
  try {
    sourceAcceptanceStore.toggleAsset(assetCode)
  } catch (error) {
    message.warning(error instanceof Error ? error.message : '无法选择当前影像')
  }
}

const submit = async (): Promise<void> => {
  try {
    const response = await sourceAcceptanceStore.acceptBatch()
    emit(
      'success',
      `源级原子承认 ${response.item_count} 景、${response.accepted_step_count} 个步骤`,
    )
  } catch {
    return
  }
}

watch(
  () => props.open,
  (open) => {
    if (open) void sourceAcceptanceStore.initialize()
  },
  { immediate: true },
)
</script>

<template>
  <a-modal
    class="source-acceptance-batch-modal"
    :open="props.open"
    title="多景源产品级别原子承认"
    width="980px"
    :confirm-loading="acceptingRef"
    :mask-closable="!acceptingRef"
    :keyboard="!acceptingRef"
    :closable="!acceptingRef"
    :ok-button-props="{ disabled: !canSubmitComputed }"
    :cancel-button-props="{ disabled: acceptingRef }"
    :ok-text="`原子承认 ${selectedAssetsComputed.length} 景 / ${selectedAssetsComputed.length * 2} 步骤`"
    cancel-text="关闭"
    @ok="submit"
    @cancel="emit('update:open', false)"
  >
    <a-alert
      type="warning"
      show-icon
      message="只承认受支持源产品已经具备的科学处理能力"
      description="服务端会先复核全部实体的受控路径、文件大小、SHA-256、产品族、STAC 标度、浮点反射率、公开许可和处理级别，再在一个事务内满足辐射定标与大气校正要求。不会复制文件，也不会执行或声称执行 DOS1、6S、FLAASH、LEDAPS 或 LaSRC。"
    />

    <section class="candidate-section">
      <header>
        <span>
          <small>ELIGIBLE SOURCE PRODUCTS</small>
          <strong>待处理 L2A/L2 业务影像</strong>
        </span>
        <a-tag :color="canProcessComputed ? 'green' : 'red'">
          {{ canProcessComputed ? '具备影像处理权限' : '当前身份无处理权限' }}
        </a-tag>
      </header>
      <a-empty
        v-if="!eligibleAssetsComputed.length"
        :image="null"
        description="当前没有同时待处理辐射定标和大气校正的受控 L2A/L2 业务影像"
      />
      <div v-else class="candidate-list">
        <article
          v-for="asset in eligibleAssetsComputed"
          :key="asset.asset_code"
          :class="{ selected: selectedAssetCodesRef.includes(asset.asset_code) }"
          @click="toggleAsset(asset.asset_code)"
        >
          <input
            type="checkbox"
            :checked="selectedAssetCodesRef.includes(asset.asset_code)"
            @click.stop="toggleAsset(asset.asset_code)"
          >
          <span>
            <strong>{{ asset.asset_name }}</strong>
            <small>{{ asset.asset_code }} · {{ asset.acquired_at.slice(0, 10) }}</small>
          </span>
          <div>
            <a-tag color="blue">{{ asset.processing_level }}</a-tag>
            <small>{{ asset.sensor_type }} · {{ asset.file_size_bytes || 0 }} bytes</small>
          </div>
        </article>
      </div>
    </section>

    <section class="evidence-section">
      <label>
        <span>承认依据</span>
        <a-textarea
          v-model:value="justificationRef"
          :rows="3"
          :maxlength="500"
          :disabled="acceptingRef"
          placeholder="至少 10 个字符，说明源产品、标度与血缘复核依据"
        />
      </label>
      <a-checkbox v-model:checked="confirmationRef" :disabled="acceptingRef">
        我确认本批次仅复用每景已校验源实体，不执行重复算法，也不把承认描述为算法运行
      </a-checkbox>
      <small>
        已选择 {{ selectedAssetsComputed.length }}/{{ sourceAcceptanceStore.maxBatchItems }} 景，
        将写入 {{ selectedAssetsComputed.length * 2 }} 条步骤证据和一个统一批次审核事件。
      </small>
    </section>

    <a-alert
      v-if="errorRef"
      type="error"
      show-icon
      :message="errorRef"
    />
    <a-alert
      v-else-if="validationMessagesComputed.length && selectedAssetsComputed.length"
      type="info"
      show-icon
      :message="validationMessagesComputed[0]"
    />

    <a-alert
      v-if="lastResultRef"
      type="success"
      show-icon
      :message="`批次 ${lastResultRef.acceptance_code} 已原子承认 ${lastResultRef.accepted_step_count} 个步骤`"
      :description="`操作人 ${lastResultRef.imported_by} · ${lastResultRef.imported_by_role} · 未复制源文件`"
    >
      <template #icon><CheckCircleOutlined /></template>
    </a-alert>
    <div v-if="lastResultRef" class="result-ledger">
      <span v-for="item in lastResultRef.items" :key="item.asset_code">
        <SafetyCertificateOutlined />
        <strong>{{ item.asset_code }}</strong>
        <small>{{ item.processor_version }} · SHA-256 {{ item.source_checksum_sha256 }}</small>
      </span>
    </div>
  </a-modal>
</template>

<style scoped>
.candidate-section, .evidence-section { display: grid; gap: 10px; margin-top: 14px; }
.candidate-section > header { display: flex; align-items: center; justify-content: space-between; }
.candidate-section > header > span { display: flex; flex-direction: column; }
.candidate-section small, .evidence-section small, .result-ledger small { font-size: 9px; color: #78857e; }
.candidate-section strong, .result-ledger strong { font-size: 11px; color: #2c4e3b; }
.candidate-list { display: grid; max-height: 310px; gap: 7px; overflow: auto; }
.candidate-list article { display: grid; grid-template-columns: 18px minmax(0, 1fr) auto; gap: 10px; align-items: center; padding: 10px; cursor: pointer; background: #fafcfb; border: 1px solid #e1e7e4; border-radius: 6px; }
.candidate-list article.selected { background: #eef7f1; border-color: #599572; }
.candidate-list article > span, .candidate-list article > div { display: flex; flex-direction: column; }
.candidate-list article > div { align-items: flex-end; }
.evidence-section { padding: 12px; background: #f7f9f8; border: 1px solid #e0e7e3; border-radius: 6px; }
.evidence-section label { display: grid; gap: 6px; }
.evidence-section label > span { font-size: 10px; color: #596b61; }
.result-ledger { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; margin-top: 10px; }
.result-ledger > span { display: grid; grid-template-columns: 18px minmax(0, 1fr); gap: 3px 7px; padding: 8px; background: #eef7f1; border: 1px solid #d4e7da; border-radius: 5px; }
.result-ledger small { grid-column: 2; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 760px) {
  .candidate-list article { grid-template-columns: 18px minmax(0, 1fr); }
  .candidate-list article > div { grid-column: 2; align-items: flex-start; }
  .result-ledger { grid-template-columns: 1fr; }
}
</style>
