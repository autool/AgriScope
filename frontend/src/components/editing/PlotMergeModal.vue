<script setup lang="ts">
import { message } from 'ant-design-vue'
import { computed, ref, watch } from 'vue'

import PlotCustomAttributeEditor from '@/components/editing/PlotCustomAttributeEditor.vue'
import { usePlotAttributeFieldStore } from '@/store/plotAttributeFieldStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type { CustomAttributeValues } from '@/types/plotAttributeField'
import type { PlotAttributes, PlotMergeDraftPayload } from '@/types/workbench'

interface PlotMergeModalProps {
  open: boolean
  items: PlotAttributes[]
  loading: boolean
}

const props = defineProps<PlotMergeModalProps>()
const emit = defineEmits<{
  cancel: []
  submit: [payload: PlotMergeDraftPayload]
}>()
const fieldStore = usePlotAttributeFieldStore()
const workbenchStore = useWorkbenchStore()

const ownerVillageRef = ref<string>('')
const landClassRef = ref<string | null>(null)
const cropTypeRef = ref<string | null>(null)
const plantingModeRef = ref<string | null>(null)
const irrigationConditionRef = ref<string | null>(null)
const commentRef = ref<string>('')
const customAttributesRef = ref<CustomAttributeValues>({})

const landClassOptions = ['耕地', '园地', '林地', '草地', '水域', '建设用地']
const cropTypeOptions = ['水稻', '玉米', '小麦', '大豆', '马铃薯', '蔬菜']
const plantingModeOptions = ['单季种植', '复种', '轮作', '间作', '设施种植']
const irrigationOptions = ['良好', '一般', '较差', '无灌排设施']

const uniqueValues = <T>(values: T[]): T[] => [...new Set(values)]
const getCommonValue = <T>(values: T[]): T | null => {
  const unique = uniqueValues(values)
  return unique.length === 1 ? unique[0] ?? null : null
}

const conflictFieldsComputed = computed<string[]>(() => [
  ['权属村', props.items.map((item) => item.owner_village)],
  ['一级地类', props.items.map((item) => item.land_class)],
  ['作物类型', props.items.map((item) => item.crop_type)],
  ['种植模式', props.items.map((item) => item.planting_mode)],
  ['灌排条件', props.items.map((item) => item.irrigation_condition)],
].filter(([, values]) => uniqueValues(values as unknown[]).length > 1)
  .map(([label]) => label as string)
  .concat(
    fieldStore.activeFieldsComputed
      .filter((field) => uniqueValues(
        props.items.map((item) => item.custom_attributes[field.field_code]),
      ).length > 1)
      .map((field) => field.label),
  ))

const cropRequiredComputed = computed<boolean>(() => landClassRef.value === '耕地')

const resetForm = (): void => {
  ownerVillageRef.value = getCommonValue(
    props.items.map((item) => item.owner_village),
  ) || ''
  landClassRef.value = getCommonValue(
    props.items.map((item) => item.land_class),
  )
  cropTypeRef.value = getCommonValue(
    props.items.map((item) => item.crop_type),
  )
  plantingModeRef.value = getCommonValue(
    props.items.map((item) => item.planting_mode),
  )
  irrigationConditionRef.value = getCommonValue(
    props.items.map((item) => item.irrigation_condition),
  )
  customAttributesRef.value = Object.fromEntries(
    fieldStore.activeFieldsComputed.map((field) => [
      field.field_code,
      getCommonValue(
        props.items.map((item) => item.custom_attributes[field.field_code]),
      ),
    ]),
  )
  commentRef.value = ''
}

const handleLandClassChange = (value: string): void => {
  landClassRef.value = value
  if (value !== '耕地') cropTypeRef.value = null
}

const submit = (): void => {
  if (props.items.length < 2) {
    message.warning('合并至少需要两个图斑')
    return
  }
  if (!ownerVillageRef.value.trim()) {
    message.warning('请确认合并后的权属村')
    return
  }
  if (!landClassRef.value) {
    message.warning('请确认合并后的一级地类')
    return
  }
  if (cropRequiredComputed.value && !cropTypeRef.value) {
    message.warning('耕地图斑必须确认作物类型')
    return
  }
  if (commentRef.value.trim().length < 8) {
    message.warning('请填写至少 8 个字符的合并依据')
    return
  }
  const missingCustomField = fieldStore.activeFieldsComputed.find(
    (field) => field.required && customAttributesRef.value[field.field_code] == null,
  )
  if (missingCustomField) {
    message.warning(`请确认自定义必填字段“${missingCustomField.label}”`)
    return
  }
  emit('submit', {
    plot_codes: props.items.map((item) => item.plot_code),
    owner_village: ownerVillageRef.value.trim(),
    land_class: landClassRef.value,
    crop_type: cropRequiredComputed.value ? cropTypeRef.value : null,
    planting_mode: plantingModeRef.value,
    irrigation_condition: irrigationConditionRef.value,
    custom_attributes: customAttributesRef.value,
    comment: commentRef.value.trim(),
  })
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      void fieldStore.load(workbenchStore.projectCodeComputed).then(resetForm)
    }
  },
)
</script>

<template>
  <a-modal
    :open="props.open"
    title="确认合并属性"
    width="620px"
    :confirm-loading="props.loading"
    :mask-closable="false"
    ok-text="执行合并"
    cancel-text="返回选择"
    @ok="submit"
    @cancel="emit('cancel')"
  >
    <div class="merge-summary">
      <strong>{{ props.items.length }} 个源图斑</strong>
      <span>{{ props.items.map((item) => item.plot_code).join('、') }}</span>
    </div>
    <a-alert
      v-if="conflictFieldsComputed.length"
      type="warning"
      show-icon
      :message="`检测到属性冲突：${conflictFieldsComputed.join('、')}`"
      description="系统不会自动选择任一源图斑属性，请人工确认合并结果。"
    />
    <a-alert
      v-else
      type="success"
      show-icon
      message="源图斑属性一致，已自动预填"
    />

    <a-form layout="vertical" class="merge-form">
      <div class="form-grid">
        <a-form-item label="合并后权属村" required>
          <a-input v-model:value="ownerVillageRef" placeholder="请确认真实权属村" />
        </a-form-item>
        <a-form-item label="合并后一级地类" required>
          <a-select
            :value="landClassRef || undefined"
            placeholder="请选择一级地类"
            @change="handleLandClassChange"
          >
            <a-select-option v-for="item in landClassOptions" :key="item" :value="item">
              {{ item }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="作物类型" :required="cropRequiredComputed">
          <a-select
            v-model:value="cropTypeRef"
            allow-clear
            :disabled="!cropRequiredComputed"
            :placeholder="cropRequiredComputed ? '请选择作物' : '非耕地不适用'"
          >
            <a-select-option v-for="item in cropTypeOptions" :key="item" :value="item">
              {{ item }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="种植模式">
          <a-select v-model:value="plantingModeRef" allow-clear placeholder="请选择种植模式">
            <a-select-option v-for="item in plantingModeOptions" :key="item" :value="item">
              {{ item }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="灌排条件">
          <a-select v-model:value="irrigationConditionRef" allow-clear placeholder="请选择灌排条件">
            <a-select-option v-for="item in irrigationOptions" :key="item" :value="item">
              {{ item }}
            </a-select-option>
          </a-select>
        </a-form-item>
      </div>
      <a-divider orientation="left">项目自定义属性</a-divider>
      <a-empty
        v-if="!fieldStore.activeFieldsComputed.length"
        :image="null"
        description="项目尚未配置自定义字段"
      />
      <PlotCustomAttributeEditor
        v-else
        :fields="fieldStore.activeFieldsComputed"
        :values="customAttributesRef"
        @change="(code, value) => customAttributesRef = { ...customAttributesRef, [code]: value }"
      />
      <a-form-item label="合并依据" required>
        <a-textarea
          v-model:value="commentRef"
          :maxlength="500"
          :auto-size="{ minRows: 3, maxRows: 6 }"
          show-count
          placeholder="例如：影像显示边界间不存在田埂，外业调查确认为同一经营地块"
        />
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<style scoped lang="less">
.merge-summary {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 10px 12px;
  margin-bottom: 12px;
  background: #f3f7f4;
  border: 1px solid #dfe8e2;
  border-radius: 6px;
}

.merge-summary strong {
  color: #295e43;
}

.merge-summary span {
  overflow: hidden;
  font-size: 10px;
  color: #7a8880;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.merge-form {
  margin-top: 14px;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 12px;
}

.merge-form :deep(.ant-form-item) {
  margin-bottom: 12px;
}
</style>
