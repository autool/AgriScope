<script setup lang="ts">
import { CloseOutlined, MergeCellsOutlined } from '@ant-design/icons-vue'

import type { PlotAttributes } from '@/types/workbench'

interface PlotMergeTrayProps {
  items: PlotAttributes[]
}

const props = defineProps<PlotMergeTrayProps>()
const emit = defineEmits<{
  remove: [plotCode: string]
  cancel: []
  continue: []
}>()
</script>

<template>
  <section class="merge-tray">
    <header>
      <span><MergeCellsOutlined />合并图斑选择</span>
      <button title="取消合并" @click="emit('cancel')"><CloseOutlined /></button>
    </header>
    <p>继续点击地图添加同县相邻图斑，服务端会执行最终拓扑校验。</p>
    <div class="selected-list">
      <div v-for="item in props.items" :key="item.plot_code">
        <span>
          <strong>{{ item.plot_code }}</strong>
          <small>{{ item.district_name || '--' }} · {{ item.land_class || '待分类' }}</small>
        </span>
        <button title="移除" @click="emit('remove', item.plot_code)"><CloseOutlined /></button>
      </div>
    </div>
    <footer>
      <span>已选择 <b>{{ props.items.length }}</b> / 20</span>
      <a-button
        type="primary"
        size="small"
        :disabled="props.items.length < 2"
        @click="emit('continue')"
      >
        确认属性并合并
      </a-button>
    </footer>
  </section>
</template>

<style scoped lang="less">
.merge-tray {
  position: absolute;
  bottom: 16px;
  left: 14px;
  z-index: 12;
  width: 300px;
  overflow: hidden;
  background: rgb(255 255 255 / 96%);
  border: 1px solid #cddbd3;
  border-radius: 7px;
  box-shadow: 0 8px 24px rgb(24 61 42 / 16%);
  backdrop-filter: blur(7px);
}

header,
footer,
.selected-list > div,
header > span,
.selected-list span {
  display: flex;
  align-items: center;
}

header {
  justify-content: space-between;
  padding: 9px 10px;
  color: #285d43;
  background: #eef5f1;
  border-bottom: 1px solid #dce7e1;
}

header > span {
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
}

button {
  color: #718078;
  cursor: pointer;
  background: transparent;
  border: 0;
}

p {
  padding: 8px 10px 4px;
  margin: 0;
  font-size: 10px;
  line-height: 16px;
  color: #77857d;
}

.selected-list {
  max-height: 178px;
  padding: 4px 8px;
  overflow: auto;
}

.selected-list > div {
  justify-content: space-between;
  padding: 6px 5px;
  border-bottom: 1px solid #edf1ef;
}

.selected-list span {
  align-items: flex-start;
  flex-direction: column;
}

.selected-list strong {
  font-size: 11px;
}

.selected-list small {
  font-size: 9px;
  color: #87938c;
}

footer {
  justify-content: space-between;
  padding: 8px 10px;
  font-size: 10px;
  border-top: 1px solid #e4ebe7;
}

footer b {
  color: #2d6b4c;
}
</style>
