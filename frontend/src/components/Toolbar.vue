<script setup lang="ts">
import {
  BorderOutlined,
  ClearOutlined,
  DeleteOutlined,
  EditOutlined,
  MergeCellsOutlined,
  NodeIndexOutlined,
  RedoOutlined,
  ScissorOutlined,
  SearchOutlined,
  SelectOutlined,
  UndoOutlined,
} from '@ant-design/icons-vue'
import { computed, ref } from 'vue'

import { useMapStore } from '@/store/mapStore'
import { useWorkbenchStore } from '@/store/workbenchStore'

interface ToolbarProps {
  activeTool?: string
}

const props = withDefaults(defineProps<ToolbarProps>(), {
  activeTool: 'select',
})

const emit = defineEmits<{
  search: [plotCode: string]
  'tool-change': [tool: string]
  toggle: []
  clear: []
  undo: []
  redo: []
}>()
const mapStore = useMapStore()
const workbenchStore = useWorkbenchStore()
const plotCodeRef = ref<string>('')

interface ToolDefinition {
  key: string
  label: string
  icon: object
  disabled?: boolean
  reason?: string
}

const toolsComputed = computed<ToolDefinition[]>(() => [
  { key: 'select', label: '选择', icon: SelectOutlined },
  {
    key: 'draw',
    label: '绘制地块',
    icon: BorderOutlined,
    disabled: !workbenchStore.canEditPlotsComputed,
    reason: '当前身份或任务状态不允许编辑图斑',
  },
  {
    key: 'vertex',
    label: '节点编辑',
    icon: NodeIndexOutlined,
    disabled: !mapStore.selectedPlotRef || !workbenchStore.canEditPlotsComputed,
    reason: !workbenchStore.canEditPlotsComputed
      ? '当前身份或任务状态不允许编辑图斑'
      : '请先在地图上选择图斑',
  },
  {
    key: 'split',
    label: '分割',
    icon: ScissorOutlined,
    disabled: !mapStore.selectedPlotRef || !workbenchStore.canEditPlotsComputed,
    reason: !workbenchStore.canEditPlotsComputed
      ? '当前身份或任务状态不允许分割图斑'
      : '请先在地图上选择图斑',
  },
  {
    key: 'merge',
    label: '合并',
    icon: MergeCellsOutlined,
    disabled: !mapStore.selectedPlotRef || !workbenchStore.canEditPlotsComputed,
    reason: !workbenchStore.canEditPlotsComputed
      ? '当前身份或任务状态不允许合并图斑'
      : '请先在地图上选择首个图斑',
  },
  {
    key: 'delete',
    label: '删除',
    icon: DeleteOutlined,
    disabled: !mapStore.selectedPlotRef || !workbenchStore.canEditPlotsComputed,
    reason: !workbenchStore.canEditPlotsComputed
      ? '当前身份或任务状态不允许编辑图斑'
      : '请先在地图上选择图斑',
  },
])

const viewLabelComputed = computed(() => (
  mapStore.viewTypeRef === '2d' ? '2D' : '3D'
))

const submitSearch = (): void => {
  const value = plotCodeRef.value.trim()
  if (value) emit('search', value)
}

const activateTool = (tool: ToolDefinition): void => {
  if (tool.disabled) return
  emit('tool-change', tool.key)
}
</script>

<template>
  <div class="editor-toolbar">
    <div class="tool-group primary-tools">
      <button
        v-for="tool in toolsComputed"
        :key="tool.key"
        type="button"
        class="tool-button"
        :class="{ active: props.activeTool === tool.key }"
        :disabled="tool.disabled"
        :title="tool.disabled ? tool.reason : tool.label"
        @click="activateTool(tool)"
      >
        <component :is="tool.icon" />
        <span>{{ tool.label }}</span>
      </button>
    </div>

    <div class="toolbar-divider" />
    <div class="tool-group history-tools">
      <button
        type="button"
        class="icon-button"
        :disabled="!workbenchStore.plotOperationHistoryRef.can_undo || workbenchStore.historyActionLoadingRef"
        :title="workbenchStore.plotOperationHistoryRef.undo_operation
          ? `撤销${workbenchStore.plotOperationHistoryRef.undo_operation.operation_type === 'split' ? '分割' : '合并'}操作`
          : '当前没有可撤销操作'"
        @click="emit('undo')"
      >
        <UndoOutlined />
      </button>
      <button
        type="button"
        class="icon-button"
        :disabled="!workbenchStore.plotOperationHistoryRef.can_redo || workbenchStore.historyActionLoadingRef"
        :title="workbenchStore.plotOperationHistoryRef.redo_operation
          ? `重做${workbenchStore.plotOperationHistoryRef.redo_operation.operation_type === 'split' ? '分割' : '合并'}操作`
          : '当前没有可重做操作'"
        @click="emit('redo')"
      >
        <RedoOutlined />
      </button>
      <button
        type="button"
        class="icon-button"
        title="清除"
        @click="emit('clear')"
      >
        <ClearOutlined />
      </button>
    </div>

    <div class="toolbar-spacer" />
    <div class="plot-search">
      <SearchOutlined />
      <input v-model="plotCodeRef" placeholder="定位图斑编号" @keyup.enter="submitSearch">
    </div>
    <button type="button" class="view-switcher" @click="emit('toggle')">
      <EditOutlined />
      <span>{{ viewLabelComputed }} 视图</span>
      <b>{{ mapStore.viewTypeRef === '2d' ? '切换 3D' : '切换 2D' }}</b>
    </button>
  </div>
</template>

<style scoped lang="less">
.editor-toolbar,
.tool-group,
.tool-button,
.icon-button,
.plot-search,
.view-switcher {
  display: flex;
  align-items: center;
}

.editor-toolbar {
  gap: 4px;
  min-width: 0;
  padding: 6px 8px;
  background: #fff;
  border-bottom: 1px solid #dfe4e1;
}

.tool-group {
  gap: 2px;
}

.tool-button,
.icon-button,
.view-switcher {
  height: 34px;
  color: #53615a;
  cursor: pointer;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 5px;
}

.tool-button {
  flex-direction: column;
  justify-content: center;
  min-width: 48px;
  padding: 2px 6px;
  font-size: 14px;
}

.tool-button span {
  margin-top: 1px;
  font-size: 7px;
  line-height: 9px;
}

.tool-button:hover,
.icon-button:hover {
  color: #265d42;
  background: #f0f5f2;
}

.tool-button.active {
  color: #fff;
  background: #2f6d4d;
  border-color: #2f6d4d;
}

.tool-button:disabled,
.icon-button:disabled {
  color: #b7bfbb;
  cursor: not-allowed;
  background: #f7f8f8;
  border-color: transparent;
}

.tool-button:disabled:hover,
.icon-button:disabled:hover {
  color: #b7bfbb;
  background: #f7f8f8;
}

.icon-button {
  justify-content: center;
  width: 30px;
  font-size: 13px;
}

.toolbar-divider {
  width: 1px;
  height: 25px;
  margin: 0 4px;
  background: #e1e5e3;
}

.toolbar-spacer {
  flex: 1;
}

.plot-search {
  width: 138px;
  height: 30px;
  padding: 0 8px;
  color: #849089;
  background: #f5f7f6;
  border: 1px solid #e0e5e2;
  border-radius: 5px;
}

.plot-search input {
  width: 100%;
  margin-left: 6px;
  font-size: 9px;
  color: #35433c;
  outline: none;
  background: transparent;
  border: 0;
}

.view-switcher {
  gap: 5px;
  padding: 0 7px;
  margin-left: 3px;
  font-size: 9px;
  border-color: #dce2df;
}

.view-switcher b {
  padding-left: 5px;
  font-size: 8px;
  font-weight: 500;
  color: #367554;
  border-left: 1px solid #e0e4e2;
}

@media (max-width: 1320px) {
  .tool-button {
    min-width: 38px;
  }

  .tool-button span,
  .plot-search {
    display: none;
  }
}
</style>
