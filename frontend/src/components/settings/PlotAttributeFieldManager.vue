<script setup lang="ts">
import { EditOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref, watch } from 'vue'

import { usePlotAttributeFieldStore } from '@/store/plotAttributeFieldStore'
import { useUserStore } from '@/store/userStore'
import type {
  PlotAttributeField,
  PlotAttributeFieldType,
} from '@/types/plotAttributeField'

interface PlotAttributeFieldManagerProps {
  projectCode: string
}

const props = defineProps<PlotAttributeFieldManagerProps>()
const fieldStore = usePlotAttributeFieldStore()
const userStore = useUserStore()
const { itemsRef, schemaDigestRef, loadingRef, savingRef } = storeToRefs(fieldStore)
const modalOpenRef = ref<boolean>(false)
const editingFieldRef = ref<PlotAttributeField | null>(null)
const fieldCodeRef = ref<string>('')
const labelRef = ref<string>('')
const fieldTypeRef = ref<PlotAttributeFieldType>('text')
const requiredRef = ref<boolean>(false)
const optionsTextRef = ref<string>('')
const displayOrderRef = ref<number>(0)
const statusRef = ref<'active' | 'inactive'>('active')

const canManageComputed = computed<boolean>(() => (
  userStore.hasCapability('manage_plot_attribute_fields')
))
const modalTitleComputed = computed<string>(() => (
  editingFieldRef.value ? `编辑字段 ${editingFieldRef.value.field_code}` : '新增自定义字段'
))
const typeLabels: Record<PlotAttributeFieldType, string> = {
  text: '文本',
  number: '数值',
  date: '日期',
  boolean: '是/否',
  single_select: '单选',
}

const resetForm = (field?: PlotAttributeField): void => {
  editingFieldRef.value = field || null
  fieldCodeRef.value = field?.field_code || ''
  labelRef.value = field?.label || ''
  fieldTypeRef.value = field?.field_type || 'text'
  requiredRef.value = field?.required || false
  optionsTextRef.value = field?.options.join('\n') || ''
  displayOrderRef.value = field?.display_order || 0
  statusRef.value = field?.status || 'active'
}

const openCreate = (): void => {
  if (!canManageComputed.value) {
    message.warning('只有项目负责人可以维护自定义字段')
    return
  }
  resetForm()
  modalOpenRef.value = true
}

const openEdit = (field: PlotAttributeField): void => {
  if (!canManageComputed.value) {
    message.warning('当前身份仅可查看自定义字段')
    return
  }
  resetForm(field)
  modalOpenRef.value = true
}

const parseOptions = (): string[] => (
  [...new Set(optionsTextRef.value
    .split(/[\n,，]/)
    .map((item) => item.trim())
    .filter(Boolean))]
)

const submit = async (): Promise<void> => {
  const user = userStore.currentUserComputed
  if (!user || !canManageComputed.value) {
    message.warning('当前身份无权维护自定义字段')
    return
  }
  const label = labelRef.value.trim()
  if (!label) {
    message.warning('请填写字段名称')
    return
  }
  const options = fieldTypeRef.value === 'single_select' ? parseOptions() : []
  if (fieldTypeRef.value === 'single_select' && !options.length) {
    message.warning('单选字段至少配置一个选项')
    return
  }
  try {
    if (editingFieldRef.value) {
      await fieldStore.update(
        props.projectCode,
        editingFieldRef.value.field_code,
        {
          label,
          field_type: fieldTypeRef.value,
          required: requiredRef.value,
          options,
          display_order: displayOrderRef.value,
          status: statusRef.value,
          operator_code: user.user_code,
        },
      )
      message.success('字段定义已更新，相关任务质量门禁已重新打开')
    } else {
      const fieldCode = fieldCodeRef.value.trim()
      if (!/^[a-z][a-z0-9_]{1,39}$/.test(fieldCode)) {
        message.warning('字段编码须以小写字母开头，仅包含小写字母、数字和下划线')
        return
      }
      await fieldStore.create(props.projectCode, {
        field_code: fieldCode,
        label,
        field_type: fieldTypeRef.value,
        required: requiredRef.value,
        options,
        display_order: displayOrderRef.value,
        operator_code: user.user_code,
      })
      message.success('自定义字段已创建，相关任务质量门禁已重新打开')
    }
    modalOpenRef.value = false
  } catch {
    // 请求拦截器已展示后端安全错误。
  }
}

watch(
  () => props.projectCode,
  (projectCode) => {
    if (projectCode) void fieldStore.load(projectCode, true)
  },
)

onMounted(() => {
  if (props.projectCode) void fieldStore.load(props.projectCode)
})
</script>

<template>
  <section class="field-manager">
    <header>
      <span>
        <strong>地块自定义属性</strong>
        <small>字段语义版本化；Excel、质量检查、矢量成果和交付包共用同一模式</small>
      </span>
      <a-space>
        <a-tag>{{ itemsRef.filter((item) => item.status === 'active').length }} 个启用</a-tag>
        <a-button
          type="primary"
          size="small"
          :disabled="!canManageComputed"
          @click="openCreate"
        >
          <template #icon><PlusOutlined /></template>
          新增字段
        </a-button>
      </a-space>
    </header>

    <a-alert
      v-if="!canManageComputed"
      type="info"
      show-icon
      message="当前身份仅可查看字段定义"
      description="只有项目负责人可以修改字段语义、必填规则、选项和启停状态。"
    />

    <a-spin :spinning="loadingRef">
      <a-empty v-if="!itemsRef.length" description="尚未配置自定义地块属性" />
      <div v-else class="field-list">
        <article v-for="field in itemsRef" :key="field.field_code">
          <div class="field-main">
            <span>
              <strong>{{ field.label }}</strong>
              <code>{{ field.field_code }}</code>
            </span>
            <a-space size="small">
              <a-tag :color="field.status === 'active' ? 'green' : 'default'">
                {{ field.status === 'active' ? '启用' : '停用' }}
              </a-tag>
              <a-tag>{{ typeLabels[field.field_type] }}</a-tag>
              <a-tag v-if="field.required" color="red">必填</a-tag>
            </a-space>
          </div>
          <p v-if="field.options.length">选项：{{ field.options.join('、') }}</p>
          <footer>
            <span>顺序 {{ field.display_order }} · 定义 v{{ field.version }} · {{ field.updated_by }}</span>
            <a-button
              type="text"
              size="small"
              :disabled="!canManageComputed"
              @click="openEdit(field)"
            >
              <template #icon><EditOutlined /></template>
              编辑
            </a-button>
          </footer>
        </article>
      </div>
    </a-spin>
    <div class="schema-digest">
      <small>当前活动字段模式 SHA-256</small>
      <code>{{ schemaDigestRef || '--' }}</code>
    </div>

    <a-modal
      :open="modalOpenRef"
      :title="modalTitleComputed"
      :confirm-loading="savingRef"
      :mask-closable="false"
      ok-text="保存定义"
      @ok="submit"
      @cancel="modalOpenRef = false"
    >
      <a-form layout="vertical">
        <div class="form-grid">
          <a-form-item label="字段编码" required>
            <a-input
              v-model:value="fieldCodeRef"
              :disabled="Boolean(editingFieldRef)"
              placeholder="例如 management_mode"
            />
          </a-form-item>
          <a-form-item label="字段名称" required>
            <a-input v-model:value="labelRef" placeholder="例如经营方式" />
          </a-form-item>
          <a-form-item label="字段类型" required>
            <a-select v-model:value="fieldTypeRef">
              <a-select-option v-for="(label, code) in typeLabels" :key="code" :value="code">
                {{ label }}
              </a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="显示顺序">
            <a-input-number v-model:value="displayOrderRef" :min="0" :max="9999" />
          </a-form-item>
          <a-form-item label="是否必填">
            <a-switch v-model:checked="requiredRef" />
          </a-form-item>
          <a-form-item v-if="editingFieldRef" label="字段状态">
            <a-select v-model:value="statusRef">
              <a-select-option value="active">启用</a-select-option>
              <a-select-option value="inactive">停用并保留历史值</a-select-option>
            </a-select>
          </a-form-item>
        </div>
        <a-form-item v-if="fieldTypeRef === 'single_select'" label="单选项" required>
          <a-textarea
            v-model:value="optionsTextRef"
            :auto-size="{ minRows: 3, maxRows: 8 }"
            placeholder="每行一个选项，也支持逗号分隔"
          />
        </a-form-item>
        <a-alert
          type="warning"
          show-icon
          message="保存后会递增定义版本并重新打开项目任务质量门禁"
          description="已导出的旧 Excel 将因字段模式摘要不一致而拒绝导入；历史导入工作簿仍按当时快照复核。"
        />
      </a-form>
    </a-modal>
  </section>
</template>

<style scoped lang="less">
.field-manager { padding: 18px 20px; margin-top: 10px; background: #fff; border: 1px solid #dfe6e2; border-radius: 8px; }
.field-manager > header { display: flex; align-items: center; justify-content: space-between; padding-bottom: 12px; border-bottom: 1px solid #e5e9e7; }
.field-manager > header span { display: flex; flex-direction: column; }
.field-manager > header strong { font-size: 12px; color: #2d3a33; }
.field-manager > header small, .schema-digest small { font-size: 8px; color: #89958f; }
.field-manager > .ant-alert { margin-top: 12px; }
.field-list { display: grid; gap: 8px; margin-top: 12px; }
.field-list article { padding: 11px 12px; background: #f7f9f8; border: 1px solid #e5ebe7; border-radius: 6px; }
.field-main, .field-list footer { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.field-main > span { display: flex; align-items: baseline; gap: 8px; }
.field-main strong { font-size: 11px; }
.field-main code, .schema-digest code { font-size: 8px; color: #527160; }
.field-list p { margin: 7px 0; font-size: 9px; color: #6f7d75; }
.field-list footer { padding-top: 6px; font-size: 8px; color: #87928c; border-top: 1px dashed #dfe6e2; }
.schema-digest { display: flex; flex-direction: column; gap: 3px; padding-top: 12px; margin-top: 12px; border-top: 1px solid #e5e9e7; }
.schema-digest code { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; }
.form-grid :deep(.ant-input-number) { width: 100%; }
@media (max-width: 720px) {
  .field-manager > header, .field-main, .field-list footer { align-items: flex-start; flex-direction: column; }
  .form-grid { grid-template-columns: 1fr; }
}
</style>
