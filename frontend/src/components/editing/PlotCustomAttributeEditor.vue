<script setup lang="ts">
import type {
  CustomAttributeValue,
  CustomAttributeValues,
  PlotAttributeField,
} from '@/types/plotAttributeField'

interface PlotCustomAttributeEditorProps {
  fields: PlotAttributeField[]
  values: CustomAttributeValues
  disabled?: boolean
}

const props = withDefaults(defineProps<PlotCustomAttributeEditorProps>(), {
  disabled: false,
})
const emit = defineEmits<{
  change: [fieldCode: string, value: CustomAttributeValue]
}>()

const emitText = (fieldCode: string, value: string): void => {
  emit('change', fieldCode, value.trim() ? value : null)
}
</script>

<template>
  <div v-if="props.fields.length" class="custom-attribute-editor">
    <label v-for="field in props.fields" :key="field.field_code">
      <span>
        {{ field.label }}
        <b v-if="field.required">*</b>
        <small>{{ field.field_code }} · v{{ field.version }}</small>
      </span>
      <a-input
        v-if="field.field_type === 'text'"
        :value="typeof props.values[field.field_code] === 'string' ? props.values[field.field_code] : undefined"
        :disabled="props.disabled"
        :maxlength="500"
        placeholder="请输入文本"
        @change="emitText(field.field_code, $event.target.value)"
      />
      <a-input-number
        v-else-if="field.field_type === 'number'"
        :value="typeof props.values[field.field_code] === 'number' ? props.values[field.field_code] : undefined"
        :disabled="props.disabled"
        :precision="6"
        placeholder="请输入数值"
        @change="(value: number | null) => emit('change', field.field_code, value)"
      />
      <a-date-picker
        v-else-if="field.field_type === 'date'"
        :value-format="'YYYY-MM-DD'"
        :value="typeof props.values[field.field_code] === 'string' ? props.values[field.field_code] : undefined"
        :disabled="props.disabled"
        placeholder="请选择日期"
        @change="(value: string | null) => emit('change', field.field_code, value)"
      />
      <a-select
        v-else-if="field.field_type === 'boolean'"
        allow-clear
        :value="typeof props.values[field.field_code] === 'boolean' ? props.values[field.field_code] : undefined"
        :disabled="props.disabled"
        placeholder="请选择"
        @change="(value: boolean | undefined) => emit('change', field.field_code, value ?? null)"
      >
        <a-select-option :value="true">是</a-select-option>
        <a-select-option :value="false">否</a-select-option>
      </a-select>
      <a-select
        v-else
        allow-clear
        :value="typeof props.values[field.field_code] === 'string' ? props.values[field.field_code] : undefined"
        :disabled="props.disabled"
        placeholder="请选择"
        @change="(value: string | undefined) => emit('change', field.field_code, value ?? null)"
      >
        <a-select-option
          v-for="option in field.options"
          :key="option"
          :value="option"
        >
          {{ option }}
        </a-select-option>
      </a-select>
    </label>
  </div>
</template>

<style scoped lang="less">
.custom-attribute-editor { display: grid; gap: 10px; }
.custom-attribute-editor label { display: grid; grid-template-columns: 98px minmax(0, 1fr); gap: 8px; align-items: center; }
.custom-attribute-editor label > span { display: flex; flex-direction: column; font-size: 10px; }
.custom-attribute-editor b { margin-left: 2px; color: #d4380d; }
.custom-attribute-editor small { margin-top: 2px; font-size: 8px; color: #8b9690; }
.custom-attribute-editor :deep(.ant-input-number),
.custom-attribute-editor :deep(.ant-picker),
.custom-attribute-editor :deep(.ant-select) { width: 100%; }
</style>
