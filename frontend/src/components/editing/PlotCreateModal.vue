<script setup lang="ts">
import { message } from 'ant-design-vue'
import { computed, ref, watch } from 'vue'

import { useUserStore } from '@/store/userStore'
import type { PlotCreateDraftPayload, PolygonGeometry } from '@/types/workbench'

interface PlotCreateModalProps {
  open: boolean
  geometry: PolygonGeometry | null
  loading?: boolean
}

const props = withDefaults(defineProps<PlotCreateModalProps>(), {
  loading: false,
})
const userStore = useUserStore()

const emit = defineEmits<{
  cancel: []
  submit: [payload: PlotCreateDraftPayload]
}>()

const plotCodeRef = ref<string>('')
const ownerVillageRef = ref<string>('')
const landClassRef = ref<string>('耕地')
const cropTypeRef = ref<string | null>(null)
const plantingModeRef = ref<string | null>(null)
const irrigationConditionRef = ref<string | null>(null)
const commentRef = ref<string>('')

const landClassOptions = ['耕地', '园地', '林地', '草地', '水域', '建设用地']
const cropTypeOptions = ['水稻', '玉米', '小麦', '大豆', '马铃薯', '蔬菜']
const plantingModeOptions = ['单季种植', '复种', '轮作', '间作', '设施种植']
const irrigationOptions = ['良好', '一般', '较差', '无灌排设施']

const cropRequiredComputed = computed<boolean>(() => landClassRef.value === '耕地')

const resetForm = (): void => {
  plotCodeRef.value = ''
  ownerVillageRef.value = ''
  landClassRef.value = '耕地'
  cropTypeRef.value = null
  plantingModeRef.value = null
  irrigationConditionRef.value = null
  commentRef.value = ''
}

const handleLandClassChange = (value: string): void => {
  landClassRef.value = value
  if (value !== '耕地') cropTypeRef.value = null
}

const submit = (): void => {
  if (!props.geometry) {
    message.error('未获取到绘制边界，请重新绘制')
    return
  }
  if (!ownerVillageRef.value.trim()) {
    message.warning('请填写权属村')
    return
  }
  if (!userStore.hasCapability('edit_plots')) {
    message.warning('当前项目身份无权新建图斑')
    return
  }
  if (cropRequiredComputed.value && !cropTypeRef.value) {
    message.warning('耕地图斑必须选择作物类型')
    return
  }
  emit('submit', {
    plot_code: plotCodeRef.value.trim() || null,
    owner_village: ownerVillageRef.value.trim(),
    geometry: props.geometry,
    land_class: landClassRef.value,
    crop_type: cropTypeRef.value,
    planting_mode: plantingModeRef.value,
    irrigation_condition: irrigationConditionRef.value,
    comment: commentRef.value.trim() || null,
  })
}

watch(
  () => props.open,
  (open) => {
    if (open) resetForm()
  },
)
</script>

<template>
  <a-modal
    :open="props.open"
    title="新建人工解译图斑"
    :confirm-loading="props.loading"
    ok-text="保存图斑"
    cancel-text="取消绘制"
    width="560px"
    :ok-button-props="{ disabled: !userStore.hasCapability('edit_plots') }"
    @ok="submit"
    @cancel="emit('cancel')"
  >
    <div class="geometry-hint">
      已接收 WGS84 Polygon，保存后由 PostGIS 校验几何并计算椭球面积。
    </div>
    <a-form layout="vertical" class="plot-form">
      <div class="form-grid">
        <a-form-item label="图斑编号">
          <a-input v-model:value="plotCodeRef" placeholder="留空由系统自动生成" />
        </a-form-item>
        <a-form-item label="权属村" required>
          <a-input v-model:value="ownerVillageRef" placeholder="请输入真实权属村名称" />
        </a-form-item>
        <a-form-item label="一级地类" required>
          <a-select :value="landClassRef" @change="handleLandClassChange">
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
      <a-form-item label="操作身份">
        <strong>
          {{ userStore.currentUserComputed?.display_name || '--' }} ·
          {{ userStore.currentUserComputed?.role_name || '--' }}
        </strong>
      </a-form-item>
      <a-form-item label="解译说明">
        <a-textarea
          v-model:value="commentRef"
          :rows="3"
          placeholder="说明采用的业务影像、外业记录和补绘判断依据"
        />
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<style scoped lang="less">
.geometry-hint {
  padding: 9px 11px;
  margin-bottom: 14px;
  font-size: 11px;
  color: #50685c;
  background: #f1f7f3;
  border: 1px solid #dce9e1;
  border-radius: 5px;
}

.plot-form :deep(.ant-form-item) { margin-bottom: 12px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; }
</style>
