<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

import { useLayerStore } from '@/store/layerStore'
import { useMapStore } from '@/store/mapStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  GeoJsonFeature,
  LineStringGeometry,
  PolygonGeometry,
} from '@/types/workbench'
import CesiumViewer from './CesiumViewer.vue'
import OlViewer from './OlViewer.vue'

interface MapViewerExpose {
  startPolygonDraw?: () => boolean
  startVertexEdit?: () => boolean
  startSplitLineDraw?: () => boolean
  flyToFeature: (feature: GeoJsonFeature) => void
  clearEditing?: () => void
  restoreFeatures?: () => void
  clearSelection?: () => void
}

const emit = defineEmits<{
  'coordinate-picked': [coordinate: { lon: number; lat: number }]
  'geometry-drawn': [geometry: PolygonGeometry]
  'geometry-modified': [geometry: PolygonGeometry]
  'split-line-drawn': [geometry: LineStringGeometry]
}>()
const mapStore = useMapStore()
const layerStore = useLayerStore()
const workbenchStore = useWorkbenchStore()
const olViewerRef = ref<MapViewerExpose | null>(null)
const cesiumViewerRef = ref<MapViewerExpose | null>(null)
const cesiumActivatedRef = ref<boolean>(mapStore.viewTypeRef === '3d')
const boundaryVisibleComputed = computed<boolean>(() => (
  layerStore.layersRef.find((layer) => layer.key === 'boundary')?.visible ?? true
))
const cityCountComputed = computed<number>(() => (
  layerStore.administrativeHierarchyComputed[0]?.children?.length || 0
))
const districtCountComputed = computed<number>(() => (
  layerStore.administrativeHierarchyComputed[0]?.children?.reduce(
    (total, city) => total + (city.children?.length || 0),
    0,
  ) || 0
))
const coveredDistrictCountComputed = computed<number>(() => (
  layerStore.farmlandHierarchyComputed[0]?.children?.reduce(
    (total, city) => total + (city.children?.filter((district) => district.count > 0).length || 0),
    0,
  ) || 0
))
const totalPlotCountComputed = computed<number>(() => (
  layerStore.plotCatalogRef?.total_count || 0
))
const viewportStatusComputed = computed<string>(() => {
  if (workbenchStore.viewportLoadingRef) return '正在加载当前视野完整地块…'
  if (workbenchStore.viewportOverviewModeRef) {
    return `省级层级概览 · 放大到县区后加载 ${totalPlotCountComputed.value} 个地块边界`
  }
  if (workbenchStore.viewportRequiresZoomRef) {
    return `当前范围包含 ${workbenchStore.viewportMatchedCountRef} 个地块，超过单次完整加载上限，请继续放大`
  }
  return `当前视野已完整加载 ${workbenchStore.viewportMatchedCountRef} 个地块 / 全任务 ${totalPlotCountComputed.value} 个`
})

watch(
  () => mapStore.viewTypeRef,
  (viewType) => {
    if (viewType === '3d') cesiumActivatedRef.value = true
  },
)

const startDraw = async (): Promise<boolean> => {
  if (mapStore.viewTypeRef !== '2d') {
    mapStore.setViewType('2d')
    await nextTick()
  }
  return olViewerRef.value?.startPolygonDraw?.() ?? false
}

const startVertexEdit = async (): Promise<boolean> => {
  if (mapStore.viewTypeRef !== '2d') {
    mapStore.setViewType('2d')
    await nextTick()
  }
  return olViewerRef.value?.startVertexEdit?.() ?? false
}

const startSplit = async (): Promise<boolean> => {
  if (mapStore.viewTypeRef !== '2d') {
    mapStore.setViewType('2d')
    await nextTick()
  }
  return olViewerRef.value?.startSplitLineDraw?.() ?? false
}

const flyTo = (feature: GeoJsonFeature): void => {
  if (mapStore.viewTypeRef === '2d') {
    olViewerRef.value?.flyToFeature(feature)
  } else {
    cesiumViewerRef.value?.flyToFeature(feature)
  }
}

const clear = (): void => {
  olViewerRef.value?.clearEditing?.()
  cesiumViewerRef.value?.clearSelection?.()
}

const restoreFeatures = (): void => {
  olViewerRef.value?.restoreFeatures?.()
}

defineExpose({ startDraw, startVertexEdit, startSplit, flyTo, clear, restoreFeatures })
</script>

<template>
  <div class="map-container">
    <OlViewer
      ref="olViewerRef"
      class="map-view"
      :class="{ 'map-view-active': mapStore.viewTypeRef === '2d' }"
      @coordinate-picked="(coordinate) => emit('coordinate-picked', coordinate)"
      @geometry-drawn="(geometry) => emit('geometry-drawn', geometry)"
      @geometry-modified="(geometry) => emit('geometry-modified', geometry)"
      @split-line-drawn="(geometry) => emit('split-line-drawn', geometry)"
    />
    <CesiumViewer
      v-if="cesiumActivatedRef"
      ref="cesiumViewerRef"
      class="map-view"
      :class="{ 'map-view-active': mapStore.viewTypeRef === '3d' }"
      @coordinate-picked="(coordinate) => emit('coordinate-picked', coordinate)"
    />
    <div class="view-indicator">
      <span>{{ mapStore.viewTypeRef === '2d' ? '二维地图' : '三维地球' }}</span>
      <strong>{{ mapStore.centerRef[0].toFixed(4) }}, {{ mapStore.centerRef[1].toFixed(4) }}</strong>
    </div>
    <div v-if="boundaryVisibleComputed" class="boundary-legend">
      <div>
        <strong>省域 → 地级区域 → 作业大区 → 真实小地块</strong>
        <small>{{ cityCountComputed }} 地级 · {{ districtCountComputed }} 真实县界 · {{ coveredDistrictCountComputed }} 作业大区</small>
        <em>{{ totalPlotCountComputed }} 个真实小地块；目录与地图几何分离加载</em>
      </div>
      <span><i class="province" />省界</span>
      <span><i class="city" />地级界</span>
      <span><i class="district" />县区界</span>
      <span><i class="farmland" />耕地</span>
      <span><i class="orchard" />园地</span>
      <span><i class="forest" />林地</span>
      <span><i class="meadow" />草地</span>
      <span><i class="water" />水域</span>
      <span><i class="construction" />建设用地</span>
    </div>
    <div
      class="viewport-status"
      :class="{
        loading: workbenchStore.viewportLoadingRef,
        warning: workbenchStore.viewportRequiresZoomRef,
      }"
    >
      {{ viewportStatusComputed }}
    </div>
    <div class="map-attribution">
      影像 © Esri, Maxar, Earthstar Geographics
    </div>
  </div>
</template>

<style scoped lang="less">
.map-container {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: #dfe7e1;
}

.map-view {
  position: absolute;
  inset: 0;
  visibility: hidden;
  pointer-events: none;
}

.map-view-active {
  visibility: visible;
  pointer-events: auto;
}

.view-indicator {
  position: absolute;
  left: 50%;
  bottom: 14px;
  z-index: 8;
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 7px 10px;
  font-size: 11px;
  color: #dbe8df;
  pointer-events: none;
  background: rgb(19 46 35 / 82%);
  border: 1px solid rgb(255 255 255 / 16%);
  border-radius: 5px;
  backdrop-filter: blur(6px);
  transform: translateX(-50%);
}

.view-indicator strong {
  font-family: "SFMono-Regular", Consolas, monospace;
  font-weight: 500;
  color: #fff;
}

.map-attribution {
  position: absolute;
  right: 10px;
  bottom: 9px;
  z-index: 8;
  padding: 4px 7px;
  font-size: 10px;
  line-height: 16px;
  color: #5f6d65;
  background: rgb(255 255 255 / 86%);
  border-radius: 4px;
  backdrop-filter: blur(4px);
}

.viewport-status {
  position: absolute;
  top: 12px;
  left: 54px;
  z-index: 8;
  max-width: 360px;
  padding: 6px 9px;
  font-size: 9px;
  color: #356047;
  pointer-events: none;
  background: rgb(255 255 255 / 90%);
  border: 1px solid rgb(54 104 78 / 18%);
  border-radius: 5px;
  backdrop-filter: blur(5px);
}

.viewport-status.loading {
  color: #2f6990;
}

.viewport-status.warning {
  color: #9a6322;
  background: rgb(255 249 235 / 94%);
  border-color: rgb(196 126 44 / 30%);
}

.boundary-legend {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 8;
  display: grid;
  grid-template-columns: repeat(3, auto);
  gap: 7px 11px;
  align-items: center;
  padding: 8px 10px;
  color: #405149;
  pointer-events: none;
  background: rgb(255 255 255 / 90%);
  border: 1px solid rgb(54 104 78 / 16%);
  border-radius: 5px;
  backdrop-filter: blur(5px);
}

.boundary-legend > div {
  display: flex;
  grid-column: 1 / -1;
  flex-wrap: wrap;
  gap: 1px 12px;
  align-items: baseline;
  min-width: 214px;
}

.boundary-legend strong {
  font-size: 10px;
  color: #274c39;
}

.boundary-legend small {
  font-size: 8px;
  color: #7b8982;
}

.boundary-legend em {
  flex-basis: 100%;
  font-style: normal;
  font-size: 8px;
  color: #4f7661;
}

.boundary-legend span {
  display: flex;
  gap: 5px;
  align-items: center;
  font-size: 9px;
}

.boundary-legend i {
  display: block;
  width: 24px;
  height: 0;
  border-top: 1px solid #a9dff4;
}

.boundary-legend i.province {
  border-top: 3px solid #35a7df;
}

.boundary-legend i.city {
  border-top: 2px dashed #65bde9;
}

.boundary-legend i.district {
  border-top: 1px dashed #8fcfe9;
}

.boundary-legend i.farmland,
.boundary-legend i.orchard,
.boundary-legend i.forest,
.boundary-legend i.meadow,
.boundary-legend i.water,
.boundary-legend i.construction {
  height: 8px;
  border: 1px solid;
}

.boundary-legend i.farmland {
  background: rgb(221 174 64 / 30%);
  border-color: #d29b22;
}

.boundary-legend i.orchard {
  background: rgb(88 155 92 / 28%);
  border-color: #4f9655;
}

.boundary-legend i.forest {
  background: rgb(45 105 68 / 28%);
  border-color: #2f7048;
}

.boundary-legend i.meadow {
  background: rgb(96 167 143 / 28%);
  border-color: #4c9b82;
}

.boundary-legend i.water {
  background: rgb(65 145 202 / 28%);
  border-color: #3b89bf;
}

.boundary-legend i.construction {
  background: rgb(139 112 98 / 26%);
  border-color: #8b7062;
}

</style>
