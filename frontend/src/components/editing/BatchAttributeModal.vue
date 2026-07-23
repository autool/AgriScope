<script setup lang="ts">
import { message } from 'ant-design-vue'
import { computed, ref, watch } from 'vue'

import PlotCustomAttributeEditor from '@/components/editing/PlotCustomAttributeEditor.vue'
import { usePlotAttributeFieldStore } from '@/store/plotAttributeFieldStore'
import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type { CustomAttributeValues } from '@/types/plotAttributeField'
import type { BatchPlotAttributeUpdateDraft } from '@/types/workbench'

interface BatchAttributeModalProps {
  open: boolean
  plotCodes: string[]
  loading?: boolean
}

const props = withDefaults(defineProps<BatchAttributeModalProps>(), {
  loading: false,
})
const userStore = useUserStore()
const fieldStore = usePlotAttributeFieldStore()
const workbenchStore = useWorkbenchStore()
const emit = defineEmits<{
  cancel: []
  submit: [payload: BatchPlotAttributeUpdateDraft]
}>()

const landClassRef = ref<string>('耕地')
const cropTypeRef = ref<string | undefined>()
const plantingModeRef = ref<string | undefined>()
const irrigationConditionRef = ref<string | undefined>()
const commentRef = ref<string>('')
const updateCustomAttributesRef = ref<boolean>(false)
const customAttributesRef = ref<CustomAttributeValues>({})

const cropRequiredComputed = computed<boolean>(() => landClassRef.value === '耕地')
const plotPreviewComputed = computed<string>(() => {
  const preview = props.plotCodes.slice(0, 5).join('、')
  return props.plotCodes.length > 5 ? `${preview} 等` : preview
})

const landClassOptions = ['耕地', '园地', '林地', '草地', '水域', '建设用地']
const cropTypeOptions = ['水稻', '玉米', '小麦', '大豆', '马铃薯', '蔬菜']
const plantingModeOptions = ['单季种植', '复种', '轮作', '间作', '设施种植']
const irrigationOptions = ['良好', '一般', '较差', '无灌排设施']

watch(
  () => props.open,
  (open) => {
    if (!open) return
    landClassRef.value = '耕地'
    cropTypeRef.value = undefined
    plantingModeRef.value = undefined
    irrigationConditionRef.value = undefined
    commentRef.value = ''
    updateCustomAttributesRef.value = false
    customAttributesRef.value = Object.fromEntries(
      fieldStore.activeFieldsComputed.map((field) => [field.field_code, null]),
    )
    void fieldStore.load(workbenchStore.projectCodeComputed)
  },
)

watch(landClassRef, (landClass) => {
  if (landClass !== '耕地') cropTypeRef.value = undefined
})

const submit = (): void => {
  if (!props.plotCodes.length) {
    message.warning('请先勾选需要批量赋值的图斑')
    return
  }
  if (cropRequiredComputed.value && !cropTypeRef.value) {
    message.warning('耕地图斑必须选择作物类型')
    return
  }
  if (!userStore.hasCapability('edit_plots')) {
    message.warning('当前项目身份无权批量修改图斑')
    return
  }
  if (!commentRef.value.trim()) {
    message.warning('请填写影像判读或调查依据')
    return
  }
  emit('submit', {
    plot_codes: props.plotCodes,
    attributes: {
      land_class: landClassRef.value,
      crop_type: cropRequiredComputed.value ? cropTypeRef.value || null : null,
      planting_mode: plantingModeRef.value || null,
      irrigation_condition: irrigationConditionRef.value || null,
      custom_attributes: updateCustomAttributesRef.value
        ? customAttributesRef.value
        : {},
    },
    comment: commentRef.value.trim(),
  })
}
</script>

<template>
  <a-modal
    :open="props.open"
    title="批量赋值图斑属性"
    ok-text="确认赋值并生成版本"
    cancel-text="取消"
    :confirm-loading="props.loading"
    :ok-button-props="{ disabled: !userStore.hasCapability('edit_plots') }"
    :mask-closable="false"
    @cancel="emit('cancel')"
    @ok="submit"
  >
    <a-alert
      type="warning"
      show-icon
      message="仅更新当前显式勾选的图斑"
      description="系统不会自动推断作物类型。提交后每个图斑生成独立新版本，并要求重新运行质量检查。"
    />

    <dl class="selection-summary">
      <div><dt>选择数量</dt><dd>{{ props.plotCodes.length }} 个图斑</dd></div>
      <div><dt>图斑编号</dt><dd>{{ plotPreviewComputed }}</dd></div>
    </dl>

    <div class="batch-form">
      <label>
        <span>一级地类 <b>*</b></span>
        <a-select v-model:value="landClassRef" :options="landClassOptions.map((value) => ({ value, label: value }))" />
      </label>
      <label v-if="fieldStore.activeFieldsComputed.length" class="custom-toggle">
        <span>自定义属性</span>
        <a-switch
          v-model:checked="updateCustomAttributesRef"
          checked-children="批量赋值"
          un-checked-children="保持原值"
        />
      </label>
      <div
        v-if="updateCustomAttributesRef && fieldStore.activeFieldsComputed.length"
        class="custom-editor-row"
      >
        <PlotCustomAttributeEditor
          :fields="fieldStore.activeFieldsComputed"
          :values="customAttributesRef"
          @change="(code, value) => customAttributesRef = { ...customAttributesRef, [code]: value }"
        />
      </div>
      <label>
        <span>作物类型 <b v-if="cropRequiredComputed">*</b></span>
        <a-select
          v-model:value="cropTypeRef"
          allow-clear
          :disabled="!cropRequiredComputed"
          :placeholder="cropRequiredComputed ? '请选择作物' : '非耕地不适用'"
          :options="cropTypeOptions.map((value) => ({ value, label: value }))"
        />
      </label>
      <label>
        <span>种植模式</span>
        <a-select
          v-model:value="plantingModeRef"
          allow-clear
          placeholder="可选"
          :options="plantingModeOptions.map((value) => ({ value, label: value }))"
        />
      </label>
      <label>
        <span>灌排条件</span>
        <a-select
          v-model:value="irrigationConditionRef"
          allow-clear
          placeholder="可选"
          :options="irrigationOptions.map((value) => ({ value, label: value }))"
        />
      </label>
      <label>
        <span>操作身份</span>
        <strong>
          {{ userStore.currentUserComputed?.display_name || '--' }} ·
          {{ userStore.currentUserComputed?.role_name || '--' }}
        </strong>
      </label>
      <label class="comment-row">
        <span>判读依据 <b>*</b></span>
        <a-textarea
          v-model:value="commentRef"
          :rows="3"
          placeholder="说明采用的业务影像、外业调查表和属性确认依据"
        />
      </label>
    </div>
  </a-modal>
</template>

<style scoped lang="less">
.selection-summary {
  margin: 12px 0;
  padding: 8px 10px;
  background: #f6f8f7;
  border: 1px solid #e2e7e4;
  border-radius: 6px;
}

.selection-summary > div {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 8px;
  padding: 3px 0;
  font-size: 11px;
}

.selection-summary dt { color: #77847d; }
.selection-summary dd { margin: 0; word-break: break-all; }

.batch-form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 12px;
}

.batch-form label {
  display: flex;
  gap: 5px;
  flex-direction: column;
  font-size: 11px;
}

.batch-form label > span b { color: #d4380d; }
.batch-form .comment-row { grid-column: 1 / -1; }
.batch-form .custom-toggle { justify-content: space-between; }
.custom-editor-row { grid-column: 1 / -1; padding: 10px; background: #f7f9f8; border: 1px solid #e4eae6; border-radius: 6px; }
</style>
