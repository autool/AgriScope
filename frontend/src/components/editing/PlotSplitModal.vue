<script setup lang="ts">
import { computed, ref, watch } from 'vue'

interface PlotSplitModalProps {
  open: boolean
  plotCode: string | null
  loading: boolean
}

const props = defineProps<PlotSplitModalProps>()
const emit = defineEmits<{
  cancel: []
  submit: [comment: string]
}>()

const commentRef = ref<string>('')
const canSubmitComputed = computed<boolean>(() => (
  Boolean(props.plotCode)
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
  const comment = commentRef.value.trim()
  if (!canSubmitComputed.value) return
  emit('submit', comment)
}
</script>

<template>
  <a-modal
    :open="props.open"
    title="确认分割图斑"
    :closable="!props.loading"
    :mask-closable="false"
    :footer="null"
    width="480px"
    @cancel="emit('cancel')"
  >
    <div class="split-summary">
      <span>源图斑</span>
      <strong>{{ props.plotCode || '--' }}</strong>
      <small>已完成分割线绘制，服务端将使用 PostGIS 执行真实拓扑分割。</small>
    </div>

    <ul class="split-rules">
      <li>分割线必须完整穿过源图斑，并且只能生成两个有效子图斑。</li>
      <li>子图斑继承源图斑属性，面积由服务端重新计算。</li>
      <li>源图斑将软删除，子图斑加入原任务并生成不可变版本。</li>
    </ul>

    <label class="comment-field">
      <span>分割依据 <b>*</b></span>
      <a-textarea
        v-model:value="commentRef"
        :disabled="props.loading"
        :maxlength="500"
        :auto-size="{ minRows: 3, maxRows: 6 }"
        show-count
        placeholder="说明可见田埂、影像纹理或外业边界等分割依据"
      />
      <small>至少填写 8 个字符，用于版本和操作审计。</small>
    </label>

    <div class="modal-actions">
      <a-button :disabled="props.loading" @click="emit('cancel')">
        返回重绘
      </a-button>
      <a-button
        type="primary"
        :loading="props.loading"
        :disabled="!canSubmitComputed"
        @click="submit"
      >
        执行分割
      </a-button>
    </div>
  </a-modal>
</template>

<style scoped lang="less">
.split-summary {
  display: grid;
  grid-template-columns: 64px 1fr;
  gap: 4px 10px;
  padding: 12px;
  background: #f4f8f5;
  border: 1px solid #dfe9e3;
  border-radius: 6px;
}

.split-summary span,
.split-summary small,
.comment-field small {
  font-size: 11px;
  color: #7d8b83;
}

.split-summary strong {
  color: #285d43;
}

.split-summary small {
  grid-column: 1 / -1;
}

.split-rules {
  padding-left: 20px;
  margin: 14px 0;
  font-size: 12px;
  line-height: 22px;
  color: #59675f;
}

.comment-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.comment-field > span {
  font-size: 12px;
  font-weight: 600;
}

.comment-field b {
  color: #cf4131;
}

.modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 18px;
}
</style>
