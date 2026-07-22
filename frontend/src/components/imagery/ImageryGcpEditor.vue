<script setup lang="ts">
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'

import type { ImageryGcpControlPointDraft } from '@/types/workbench'

interface ImageryGcpEditorProps {
  points: ImageryGcpControlPointDraft[]
  rasterWidth: number | null
  rasterHeight: number | null
}

const props = defineProps<ImageryGcpEditorProps>()
const emit = defineEmits<{
  'update:points': [points: ImageryGcpControlPointDraft[]]
}>()

const updatePoint = <K extends keyof ImageryGcpControlPointDraft>(
  index: number,
  key: K,
  value: ImageryGcpControlPointDraft[K],
): void => {
  const points = props.points.map((point, pointIndex) => (
    pointIndex === index ? { ...point, [key]: value } : point
  ))
  emit('update:points', points)
}

const addPoint = (): void => {
  emit('update:points', [
    ...props.points,
    {
      point_id: `GCP-${String(props.points.length + 1).padStart(2, '0')}`,
      pixel_column: null,
      pixel_row: null,
      x: null,
      y: null,
      z: 0,
      source: '',
    },
  ])
}

const removePoint = (index: number): void => {
  emit('update:points', props.points.filter((_, pointIndex) => pointIndex !== index))
}
</script>

<template>
  <section class="gcp-editor">
    <header>
      <span>
        <strong>地面控制点</strong>
        <small>
          影像 {{ rasterWidth || '--' }} × {{ rasterHeight || '--' }} 像素；至少 3 个不共线点，建议 4 个以上
        </small>
      </span>
      <a-button size="small" @click="addPoint"><PlusOutlined /> 添加控制点</a-button>
    </header>
    <a-alert
      type="warning"
      show-icon
      message="控制点必须来自实测、测绘成果或可追溯高精度参考资料；平台不会自动填充虚构坐标。"
    />
    <div class="gcp-table">
      <div class="gcp-row gcp-head">
        <span>编号</span><span>像素列</span><span>像素行</span><span>地面 X</span><span>地面 Y</span><span>高程</span><span>来源</span><span />
      </div>
      <div v-for="(point, index) in points" :key="`${point.point_id}-${index}`" class="gcp-row">
        <a-input :value="point.point_id" @update:value="updatePoint(index, 'point_id', $event)" />
        <a-input-number
          :value="point.pixel_column"
          :min="0"
          :max="rasterWidth ? rasterWidth - 1 : undefined"
          @update:value="updatePoint(index, 'pixel_column', $event)"
        />
        <a-input-number
          :value="point.pixel_row"
          :min="0"
          :max="rasterHeight ? rasterHeight - 1 : undefined"
          @update:value="updatePoint(index, 'pixel_row', $event)"
        />
        <a-input-number :value="point.x" :precision="8" @update:value="updatePoint(index, 'x', $event)" />
        <a-input-number :value="point.y" :precision="8" @update:value="updatePoint(index, 'y', $event)" />
        <a-input-number :value="point.z" :precision="3" @update:value="updatePoint(index, 'z', $event)" />
        <a-input :value="point.source" placeholder="实测批次或资料名称" @update:value="updatePoint(index, 'source', $event)" />
        <a-button
          type="text"
          danger
          :disabled="points.length <= 3"
          @click="removePoint(index)"
        >
          <DeleteOutlined />
        </a-button>
      </div>
      <a-empty v-if="!points.length" :image="false" description="添加真实控制点后才能执行 GCP 精校正" />
    </div>
  </section>
</template>

<style scoped>
.gcp-editor { display: grid; grid-column: 1 / -1; gap: 9px; padding: 10px; background: #f7f9f8; border: 1px solid #dfe6e2; border-radius: 6px; }
.gcp-editor > header { display: flex; align-items: center; justify-content: space-between; }
.gcp-editor > header span { display: flex; flex-direction: column; }
.gcp-editor strong { font-size: 10px; }
.gcp-editor small { font-size: 8px; color: #7d8a83; }
.gcp-table { display: grid; gap: 5px; overflow-x: auto; }
.gcp-row { display: grid; grid-template-columns: 86px 82px 82px 112px 112px 82px minmax(150px, 1fr) 32px; gap: 5px; min-width: 780px; align-items: center; }
.gcp-head { font-size: 8px; color: #748179; }
.gcp-row :deep(.ant-input-number) { width: 100%; }
</style>
