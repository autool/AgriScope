<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type { PlotOperationSummary } from '@/types/workbench'

interface PlotHistoryActionModalProps {
  open: boolean
  action: 'undo' | 'redo'
  operation: PlotOperationSummary | null
  loading: boolean
}

const props = defineProps<PlotHistoryActionModalProps>()
const emit = defineEmits<{
  cancel: []
  submit: [comment: string]
}>()

const commentRef = ref<string>('')
const actionLabelComputed = computed<string>(() => (
  props.action === 'undo' ? '撤销' : '重做'
))
const operationLabelComputed = computed<string>(() => (
  props.operation?.operation_type === 'split' ? '分割' : '合并'
))
const canSubmitComputed = computed<boolean>(() => (
  Boolean(props.operation)
  && commentRef.value.trim().length >= 8
  && !props.loading
))

watch(
  () => props.open,
  (open) => {
    if (open) commentRef.value = ''
  },
)

const submit = (): void => {
  if (!canSubmitComputed.value) return
  emit('submit', commentRef.value.trim())
}
</script>

<template>
  <a-modal
    :open="props.open"
    :title="`${actionLabelComputed}${operationLabelComputed}操作`"
    :footer="null"
    :mask-closable="false"
    width="500px"
    @cancel="emit('cancel')"
  >
    <div v-if="props.operation" class="operation-summary">
      <span>操作编号</span><strong>{{ props.operation.operation_code }}</strong>
      <span>源图斑</span><small>{{ props.operation.source_plot_codes.join('、') }}</small>
      <span>结果图斑</span><small>{{ props.operation.result_plot_codes.join('、') }}</small>
    </div>
    <a-alert
      type="warning"
      show-icon
      :message="`${actionLabelComputed}会生成新的不可变版本，不会删除历史记录`"
      description="若关联图斑已产生后续版本，服务端将拒绝覆盖新编辑。"
    />
    <label class="comment-field">
      <span>{{ actionLabelComputed }}依据 <b>*</b></span>
      <a-textarea
        v-model:value="commentRef"
        :maxlength="500"
        :disabled="props.loading"
        :auto-size="{ minRows: 3, maxRows: 6 }"
        show-count
        placeholder="请说明误操作原因、复核证据或恢复依据，至少 8 个字符"
      />
    </label>
    <div class="modal-actions">
      <a-button :disabled="props.loading" @click="emit('cancel')">取消</a-button>
      <a-button
        type="primary"
        :loading="props.loading"
        :disabled="!canSubmitComputed"
        @click="submit"
      >
        确认{{ actionLabelComputed }}
      </a-button>
    </div>
  </a-modal>
</template>

<style scoped lang="less">
.operation-summary {
  display: grid;
  grid-template-columns: 62px 1fr;
  gap: 6px 10px;
  padding: 10px 12px;
  margin-bottom: 12px;
  background: #f3f7f4;
  border: 1px solid #dfe8e2;
  border-radius: 6px;
}

.operation-summary span,
.operation-summary small {
  font-size: 10px;
  color: #7a8780;
}

.operation-summary strong {
  color: #2d6247;
}

.comment-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 14px;
}

.comment-field > span {
  font-size: 12px;
  font-weight: 600;
}

.comment-field b {
  color: #ca4031;
}

.modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 18px;
}
</style>
