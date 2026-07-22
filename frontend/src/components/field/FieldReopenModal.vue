<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = defineProps<{
  open: boolean
  loading: boolean
  verificationCode: string | null
}>()

const emit = defineEmits<{
  cancel: []
  submit: [comment: string]
}>()

const commentRef = ref<string>('')
const canSubmitComputed = computed<boolean>(() => commentRef.value.trim().length >= 2)

watch(
  () => props.open,
  (open) => {
    if (open) commentRef.value = ''
  },
)
</script>

<template>
  <a-modal
    :open="open"
    title="重新打开外业疑点"
    :confirm-loading="loading"
    :ok-button-props="{ disabled: !canSubmitComputed }"
    ok-text="确认重开"
    cancel-text="取消"
    @ok="canSubmitComputed && emit('submit', commentRef.trim())"
    @cancel="emit('cancel')"
  >
    <a-alert
      type="warning"
      show-icon
      :message="`将 ${verificationCode || '当前记录'} 恢复为待处置`"
      description="该操作会重新打开关联质量问题，将任务退回解译阶段并使现有审核/成果包失效；历史处置记录不会删除。"
    />
    <label class="reopen-form">
      <span>重新打开依据</span>
      <a-textarea
        v-model:value="commentRef"
        :rows="4"
        :maxlength="500"
        show-count
        placeholder="说明新增现场证据、定位修正或上次结论存在的问题"
      />
    </label>
  </a-modal>
</template>

<style scoped>
.reopen-form { display: grid; gap: 6px; margin-top: 14px; }
.reopen-form > span { font-size: 12px; font-weight: 600; color: #3e4943; }
</style>
