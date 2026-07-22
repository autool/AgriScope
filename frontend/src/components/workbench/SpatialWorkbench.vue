<script setup lang="ts">
import { message, Modal } from 'ant-design-vue'
import { ref } from 'vue'

import LayerTree from '@/components/LayerTree.vue'
import MapContainer from '@/components/MapContainer.vue'
import Toolbar from '@/components/Toolbar.vue'
import PlotCreateModal from '@/components/editing/PlotCreateModal.vue'
import PlotHistoryActionModal from '@/components/editing/PlotHistoryActionModal.vue'
import PlotMergeModal from '@/components/editing/PlotMergeModal.vue'
import PlotMergeTray from '@/components/editing/PlotMergeTray.vue'
import PlotSplitModal from '@/components/editing/PlotSplitModal.vue'
import { useMapStore } from '@/store/mapStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  LineStringGeometry,
  PlotCreateDraftPayload,
  PlotMergeDraftPayload,
  PolygonGeometry,
} from '@/types/workbench'

interface SpatialWorkbenchProps {
  editing?: boolean
}

withDefaults(defineProps<SpatialWorkbenchProps>(), {
  editing: false,
})

const workbenchStore = useWorkbenchStore()
const mapStore = useMapStore()
const mapContainerRef = ref<InstanceType<typeof MapContainer> | null>(null)
const createModalOpenRef = ref<boolean>(false)
const pendingGeometryRef = ref<PolygonGeometry | null>(null)
const splitModalOpenRef = ref<boolean>(false)
const pendingSplitLineRef = ref<LineStringGeometry | null>(null)
const activeEditingToolRef = ref<string>('select')
const mergeModalOpenRef = ref<boolean>(false)
const historyActionModalOpenRef = ref<boolean>(false)
const historyActionRef = ref<'undo' | 'redo'>('undo')

/**
 * 按编号定位图斑。
 * Args:
 *   plotCode: 图斑编号。
 * Returns:
 *   Promise<void>: 图斑定位完成后结束。
 */
const handleSearch = async (plotCode: string): Promise<void> => {
  try {
    const feature = await workbenchStore.selectByCode(plotCode)
    mapContainerRef.value?.flyTo(feature)
    message.success(`已定位图斑 ${plotCode}`)
  } catch {
    // API 拦截器已经显示安全错误提示，此处只阻止 Vue 未处理异常。
  }
}

/**
 * 处理地图点查坐标。
 * Args:
 *   coordinate: WGS84 经纬度。
 * Returns:
 *   Promise<void>: 点查和选中状态同步完成后结束。
 */
const handleCoordinatePicked = async (
  coordinate: { lon: number; lat: number },
): Promise<void> => {
  if (activeEditingToolRef.value === 'merge') {
    try {
      const added = await workbenchStore.addMergePlotByCoordinate(coordinate)
      if (added) message.success(`已加入合并选择：${added.plot_code}`)
    } catch (error) {
      if (error instanceof Error) message.warning(error.message)
    }
    return
  }
  try {
    await workbenchStore.selectByCoordinate(coordinate)
  } catch {
    workbenchStore.clearSelectedPlot()
  }
}

const confirmDelete = (): void => {
  const plotCode = workbenchStore.selectedPlotCodeComputed
  if (!plotCode) {
    message.warning('请先选择需要删除的图斑')
    return
  }
  Modal.confirm({
    title: `确认删除图斑 ${plotCode}？`,
    content: '系统将执行软删除，保留几何版本、审核日志，并解除外业匹配。',
    okText: '确认删除',
    cancelText: '取消',
    okType: 'danger',
    async onOk() {
      try {
        await workbenchStore.deleteSelectedPlot(
          '影像判读确认删除，保留版本审计',
        )
        mapContainerRef.value?.clear()
        message.success(`图斑 ${plotCode} 已软删除`)
      } catch {
        // 保持当前选中状态，便于用户修正问题后重试。
      }
    },
  })
}

const handleToolChange = async (tool: string): Promise<void> => {
  activeEditingToolRef.value = tool
  if (tool === 'select') {
    workbenchStore.cancelMergeSelection()
    mergeModalOpenRef.value = false
    mapContainerRef.value?.clear()
    mapContainerRef.value?.restoreFeatures()
    return
  }
  if (tool === 'draw') {
    workbenchStore.cancelMergeSelection()
    const started = await mapContainerRef.value?.startDraw()
    if (!started) message.error('二维绘制交互启动失败')
    return
  }
  if (tool === 'vertex') {
    workbenchStore.cancelMergeSelection()
    const started = await mapContainerRef.value?.startVertexEdit()
    if (!started) message.warning('请先选择一个可编辑图斑')
    return
  }
  if (tool === 'split') {
    workbenchStore.cancelMergeSelection()
    const started = await mapContainerRef.value?.startSplit()
    if (!started) message.warning('请先选择一个可分割图斑')
    return
  }
  if (tool === 'merge') {
    try {
      mapContainerRef.value?.clear()
      workbenchStore.beginMergeSelection()
      message.info('继续点击地图添加同县相邻图斑')
    } catch (error) {
      activeEditingToolRef.value = 'select'
      if (error instanceof Error) message.warning(error.message)
    }
    return
  }
  if (tool === 'delete') {
    workbenchStore.cancelMergeSelection()
    confirmDelete()
  }
}

const handleGeometryDrawn = (geometry: PolygonGeometry): void => {
  pendingGeometryRef.value = geometry
  createModalOpenRef.value = true
}

const handleCreateCancel = (): void => {
  createModalOpenRef.value = false
  pendingGeometryRef.value = null
  mapContainerRef.value?.clear()
}

const handleCreateSubmit = async (
  payload: PlotCreateDraftPayload,
): Promise<void> => {
  try {
    const attributes = await workbenchStore.createPlot(payload)
    createModalOpenRef.value = false
    pendingGeometryRef.value = null
    mapContainerRef.value?.clear()
    message.success(`图斑 ${attributes.plot_code} 已创建并生成 v1`)
  } catch {
    // 保留表单和绘制边界，用户可以直接修正后再次提交。
  }
}

const handleGeometryModified = (geometry: PolygonGeometry): void => {
  const plotCode = workbenchStore.selectedPlotCodeComputed
  if (!plotCode) {
    mapContainerRef.value?.restoreFeatures()
    return
  }
  Modal.confirm({
    title: `保存图斑 ${plotCode} 的节点修改？`,
    content: '保存后将重新计算椭球面积、生成新版本，并将任务重新打开为解译中。',
    okText: '保存边界',
    cancelText: '放弃修改',
    async onOk() {
      try {
        const attributes = await workbenchStore.saveSelectedPlotGeometry(
          geometry,
          '通过节点编辑调整图斑边界',
        )
        message.success(
          `图斑 ${plotCode} 边界已保存为 v${attributes.version}`,
        )
      } catch {
        mapContainerRef.value?.restoreFeatures()
      }
    },
    onCancel() {
      mapContainerRef.value?.restoreFeatures()
    },
  })
}

const handleSplitLineDrawn = (line: LineStringGeometry): void => {
  pendingSplitLineRef.value = line
  splitModalOpenRef.value = true
}

const handleSplitCancel = (): void => {
  splitModalOpenRef.value = false
  pendingSplitLineRef.value = null
  mapContainerRef.value?.clear()
}

const handleSplitSubmit = async (comment: string): Promise<void> => {
  const line = pendingSplitLineRef.value
  if (!line) return
  try {
    const result = await workbenchStore.splitSelectedPlot(line, comment)
    splitModalOpenRef.value = false
    pendingSplitLineRef.value = null
    mapContainerRef.value?.clear()
    message.success(
      `分割完成：${result.result_plots.map((item) => item.plot_code).join('、')}`,
    )
  } catch {
    // 保留分割线和表单依据，便于用户修改说明或返回重绘。
  }
}

const handleMergeRemove = (plotCode: string): void => {
  workbenchStore.removeMergePlot(plotCode)
  if (workbenchStore.mergeSelectionRef.length === 0) {
    activeEditingToolRef.value = 'select'
  }
}

const handleMergeCancel = (): void => {
  mergeModalOpenRef.value = false
  activeEditingToolRef.value = 'select'
  workbenchStore.cancelMergeSelection()
}

const handleMergeContinue = (): void => {
  if (workbenchStore.mergeSelectionRef.length < 2) {
    message.warning('请至少选择两个相邻图斑')
    return
  }
  mergeModalOpenRef.value = true
}

const handleMergeSubmit = async (
  payload: PlotMergeDraftPayload,
): Promise<void> => {
  try {
    const result = await workbenchStore.mergeSelectedPlots(payload)
    mergeModalOpenRef.value = false
    activeEditingToolRef.value = 'select'
    message.success(
      `合并完成：${result.source_plot_codes.length} 个图斑 → ${result.result_plot.plot_code}`,
    )
  } catch {
    // 保留选择和人工确认属性，便于根据服务端拓扑提示整改后重试。
  }
}

const openHistoryAction = (action: 'undo' | 'redo'): void => {
  const state = workbenchStore.plotOperationHistoryRef
  const operation = action === 'undo'
    ? state.undo_operation
    : state.redo_operation
  if (!operation) {
    message.warning(action === 'undo' ? '当前没有可撤销操作' : '当前没有可重做操作')
    return
  }
  activeEditingToolRef.value = 'select'
  workbenchStore.cancelMergeSelection()
  historyActionRef.value = action
  historyActionModalOpenRef.value = true
}

const handleHistoryActionSubmit = async (comment: string): Promise<void> => {
  try {
    const result = historyActionRef.value === 'undo'
      ? await workbenchStore.undoLastPlotOperation(comment)
      : await workbenchStore.redoLastPlotOperation(comment)
    historyActionModalOpenRef.value = false
    const label = result.action === 'undo' ? '撤销' : '重做'
    message.success(
      `${label}完成：当前活动图斑 ${result.active_plot_codes.join('、')}`,
    )
  } catch {
    // 保留操作依据，用户可根据服务端版本冲突提示核对后重试。
  }
}

const handleClear = (): void => {
  activeEditingToolRef.value = 'select'
  mergeModalOpenRef.value = false
  workbenchStore.cancelMergeSelection()
  workbenchStore.clearSelectedPlot()
  mapContainerRef.value?.clear()
}
</script>

<template>
  <div class="spatial-workbench">
    <aside class="layer-column">
      <LayerTree
        :imagery="workbenchStore.overviewRef?.imagery"
      />
    </aside>
    <main class="map-column">
      <slot name="toolbar">
        <Toolbar
          v-if="editing"
          :active-tool="activeEditingToolRef"
          @search="handleSearch"
          @tool-change="handleToolChange"
          @toggle="mapStore.toggleViewType()"
          @clear="handleClear"
          @undo="openHistoryAction('undo')"
          @redo="openHistoryAction('redo')"
        />
        <div v-else class="spatial-toolbar">
          <slot name="spatial-toolbar" />
          <a-button size="small" @click="mapStore.toggleViewType()">
            {{ mapStore.viewTypeRef === '2d' ? '切换三维' : '切换二维' }}
          </a-button>
        </div>
      </slot>
      <div class="map-stage">
        <MapContainer
          ref="mapContainerRef"
          @coordinate-picked="handleCoordinatePicked"
          @geometry-drawn="handleGeometryDrawn"
          @geometry-modified="handleGeometryModified"
          @split-line-drawn="handleSplitLineDrawn"
        />
        <PlotMergeTray
          v-if="activeEditingToolRef === 'merge'"
          :items="workbenchStore.mergeSelectionRef"
          @remove="handleMergeRemove"
          @cancel="handleMergeCancel"
          @continue="handleMergeContinue"
        />
      </div>
      <footer>
        <span>坐标系：CGCS2000 / EPSG:4490</span>
        <span>卫星影像默认底图</span>
        <span>行政区划边界：黑龙江省 / 市 / 县区全域</span>
      </footer>
    </main>
    <aside class="business-panel">
      <slot name="panel" />
    </aside>
    <PlotCreateModal
      :open="createModalOpenRef"
      :geometry="pendingGeometryRef"
      :loading="workbenchStore.creatingPlotRef"
      @cancel="handleCreateCancel"
      @submit="handleCreateSubmit"
    />
    <PlotSplitModal
      :open="splitModalOpenRef"
      :plot-code="workbenchStore.selectedPlotCodeComputed"
      :loading="workbenchStore.splittingPlotRef"
      @cancel="handleSplitCancel"
      @submit="handleSplitSubmit"
    />
    <PlotMergeModal
      :open="mergeModalOpenRef"
      :items="workbenchStore.mergeSelectionRef"
      :loading="workbenchStore.mergingPlotsRef"
      @cancel="mergeModalOpenRef = false"
      @submit="handleMergeSubmit"
    />
    <PlotHistoryActionModal
      :open="historyActionModalOpenRef"
      :action="historyActionRef"
      :operation="historyActionRef === 'undo'
        ? workbenchStore.plotOperationHistoryRef.undo_operation
        : workbenchStore.plotOperationHistoryRef.redo_operation"
      :loading="workbenchStore.historyActionLoadingRef"
      @cancel="historyActionModalOpenRef = false"
      @submit="handleHistoryActionSubmit"
    />
  </div>
</template>

<style scoped>
.spatial-workbench { display: grid; grid-template-columns: clamp(300px, 19vw, 370px) minmax(410px, 1fr) 320px; height: 100%; margin: 8px; overflow: hidden; background: #fff; border: 1px solid #dce2df; border-radius: 7px; }
.layer-column { min-width: 0; min-height: 0; border-right: 1px solid #dfe4e1; }
.map-column { display: grid; grid-template-rows: 48px minmax(0, 1fr) 24px; min-width: 0; min-height: 0; }
.spatial-toolbar { display: flex; gap: 8px; align-items: center; justify-content: space-between; padding: 0 10px; background: #fff; border-bottom: 1px solid #dfe4e1; }
.map-stage { position: relative; min-height: 0; background: #dce1de; }
footer { display: flex; gap: 18px; align-items: center; padding: 0 10px; font-size: 8px; color: #727f79; background: #f8f9f9; border-top: 1px solid #e1e5e3; }
.business-panel { min-width: 0; min-height: 0; overflow: auto; border-left: 1px solid #dfe4e1; }
</style>
