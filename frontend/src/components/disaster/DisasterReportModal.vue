<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = defineProps<{
  open: boolean
  loading: boolean
  taskCode: string
  patchCount: number
  affectedAreaHa: number
}>()

const emit = defineEmits<{
  cancel: []
  submit: [reportTitle: string, comment: string]
}>()

const reportTitleRef = ref<string>('')
const commentRef = ref<string>('')
const canSubmitComputed = computed<boolean>(() => (
  reportTitleRef.value.trim().length >= 2
  && commentRef.value.trim().length >= 4
))

watch(
  () => props.open,
  (open) => {
    if (!open) return
    reportTitleRef.value = `${props.taskCode} 农业灾害遥感监测专题报告`
    commentRef.value = ''
  },
)

/**
 * 提交报告标题和人工生成依据。
 * Returns:
 *   void: 将标准化表单交给父组件。
 */
const handleSubmit = (): void => {
  if (!canSubmitComputed.value) return
  emit(
    'submit',
    reportTitleRef.value.trim(),
    commentRef.value.trim(),
  )
}
</script>

<template>
  <a-modal
    :open="open"
    title="生成灾害监测专题报告"
    :confirm-loading="loading"
    :ok-button-props="{ disabled: !canSubmitComputed }"
    ok-text="生成 XLSX 报告"
    cancel-text="取消"
    @ok="handleSubmit"
    @cancel="emit('cancel')"
  >
    <a-alert
      type="info"
      show-icon
      :message="`将固化 ${patchCount} 个已复核斑块`"
      :description="`报告受灾面积 ${affectedAreaHa.toFixed(2)} 公顷，包含空间分布图、等级占比、类型统计、斑块明细和来源 SHA-256 审计。`"
    />
    <div class="report-form">
      <label>
        <span>报告标题</span>
        <a-input v-model:value="reportTitleRef" :maxlength="200" />
      </label>
      <label>
        <span>生成依据</span>
        <a-textarea
          v-model:value="commentRef"
          :rows="4"
          :maxlength="500"
          show-count
          placeholder="说明灾害模型批次、人工复核完成情况和报告用途"
        />
      </label>
    </div>
  </a-modal>
</template>

<style scoped>
.report-form { display: grid; gap: 12px; margin-top: 14px; }
.report-form label { display: grid; gap: 6px; }
.report-form span { font-size: 12px; font-weight: 600; color: #3f4c45; }
</style>
