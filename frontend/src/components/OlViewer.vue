<script setup lang="ts">
import Collection from 'ol/Collection.js'
import GeoJSON from 'ol/format/GeoJSON.js'
import type Feature from 'ol/Feature.js'
import type { FeatureLike } from 'ol/Feature.js'
import type Geometry from 'ol/geom/Geometry.js'
import Point from 'ol/geom/Point.js'
import Draw from 'ol/interaction/Draw.js'
import type { DrawEvent } from 'ol/interaction/Draw.js'
import Modify from 'ol/interaction/Modify.js'
import type { ModifyEvent } from 'ol/interaction/Modify.js'
import { createEmpty, extend, getCenter } from 'ol/extent.js'
import TileLayer from 'ol/layer/Tile.js'
import VectorLayer from 'ol/layer/Vector.js'
import Map from 'ol/Map.js'
import { fromLonLat, toLonLat, transformExtent } from 'ol/proj.js'
import VectorSource from 'ol/source/Vector.js'
import XYZ from 'ol/source/XYZ.js'
import { Circle as CircleStyle, Fill, Stroke, Style, Text } from 'ol/style.js'
import View from 'ol/View.js'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { useLayerStore } from '@/store/layerStore'
import { useMapStore } from '@/store/mapStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type {
  GeoJsonFeature,
  LineStringGeometry,
  PolygonGeometry,
} from '@/types/workbench'

type OlFeature = Feature<Geometry>
type OlVectorLayer = VectorLayer<VectorSource<OlFeature>>

const emit = defineEmits<{
  'coordinate-picked': [coordinate: { lon: number; lat: number }]
  'geometry-drawn': [geometry: PolygonGeometry]
  'geometry-modified': [geometry: PolygonGeometry]
  'split-line-drawn': [geometry: LineStringGeometry]
}>()
const mapStore = useMapStore()
const layerStore = useLayerStore()
const workbenchStore = useWorkbenchStore()
const targetRef = ref<HTMLDivElement | null>(null)

let map: Map | null = null
let baseLayer: TileLayer<XYZ> | null = null
let farmlandLayer: OlVectorLayer | null = null
let disasterLayer: OlVectorLayer | null = null
let boundaryLayer: OlVectorLayer | null = null
let fieldLayer: OlVectorLayer | null = null
let drawLayer: OlVectorLayer | null = null
let drawInteraction: Draw | null = null
let modifyInteraction: Modify | null = null
let syncingView = false
let suppressClickUntil = 0

const loadVisiblePlots = (): void => {
  if (!map || mapStore.viewTypeRef !== '2d') return
  const size = map.getSize()
  if (!size) return
  const extent = transformExtent(
    map.getView().calculateExtent(size),
    'EPSG:3857',
    'EPSG:4326',
  )
  void workbenchStore.loadPlotsForViewport(
    {
      min_lon: extent[0],
      min_lat: extent[1],
      max_lon: extent[2],
      max_lat: extent[3],
    },
    map.getView().getZoom() ?? mapStore.zoomRef,
  )
}

const landClassStyles: Record<string, Style> = {
  耕地: new Style({
    fill: new Fill({ color: 'rgba(221, 174, 64, 0.27)' }),
    stroke: new Stroke({ color: '#d29b22', width: 2 }),
  }),
  园地: new Style({
    fill: new Fill({ color: 'rgba(88, 155, 92, 0.25)' }),
    stroke: new Stroke({ color: '#4f9655', width: 2 }),
  }),
  林地: new Style({
    fill: new Fill({ color: 'rgba(45, 105, 68, 0.25)' }),
    stroke: new Stroke({ color: '#2f7048', width: 2 }),
  }),
  草地: new Style({
    fill: new Fill({ color: 'rgba(96, 167, 143, 0.24)' }),
    stroke: new Stroke({ color: '#4c9b82', width: 2 }),
  }),
  水域: new Style({
    fill: new Fill({ color: 'rgba(65, 145, 202, 0.24)' }),
    stroke: new Stroke({ color: '#3b89bf', width: 2 }),
  }),
  建设用地: new Style({
    fill: new Fill({ color: 'rgba(139, 112, 98, 0.23)' }),
    stroke: new Stroke({ color: '#8b7062', width: 2 }),
  }),
}

const farmlandStyle = (feature: FeatureLike): Style => (
  landClassStyles[String(feature.get('land_class') || '')] || landClassStyles.耕地
)

const selectedStyle = new Style({
  fill: new Fill({ color: 'rgba(228, 81, 54, 0.34)' }),
  stroke: new Stroke({ color: '#e3472f', width: 3 }),
})

const mergeSelectedStyle = new Style({
  fill: new Fill({ color: 'rgba(111, 74, 180, 0.30)' }),
  stroke: new Stroke({ color: '#7650b5', width: 3, lineDash: [7, 4] }),
})

const fieldStyle = (feature: FeatureLike): Style => {
  const status = feature.get('match_status')
  const color = status === 'consistent'
    ? '#4eb47a'
    : status === 'offset'
      ? '#f0a43b'
      : '#e05252'
  return new Style({
    image: new CircleStyle({
      radius: 6,
      fill: new Fill({ color }),
      stroke: new Stroke({ color: '#fff', width: 2 }),
    }),
  })
}

const disasterStyle = (feature: FeatureLike): Style => {
  const severity = feature.get('severity') as '轻度' | '中度' | '重度' | '绝收'
  const color = {
    轻度: '#f0b24b',
    中度: '#ef7f36',
    重度: '#dc4c3f',
    绝收: '#851f2b',
  }[severity] || '#df7b45'
  return new Style({
    fill: new Fill({ color: `${color}55` }),
    stroke: new Stroke({ color, width: 2.5, lineDash: [7, 4] }),
  })
}

const boundaryStyle = (feature: FeatureLike, resolution: number): Style | Style[] => {
  const level = feature.get('boundary_level') as 'province' | 'city' | 'district'
  const plotCount = Number(feature.get('plot_count') || 0)
  const boundaryName = String(feature.get('boundary_name') || '')
  const styleConfig = {
    province: {
      color: '#35a7df',
      width: 3.2,
      lineDash: undefined,
      fill: 'rgba(29, 109, 74, 0.018)',
      font: '700 13px sans-serif',
      showLabel: false,
      zIndex: 14,
    },
    city: {
      color: '#65bde9',
      width: 1.8,
      lineDash: [9, 4],
      fill: 'rgba(53, 167, 223, 0.035)',
      font: '600 11px sans-serif',
      showLabel: resolution < 5000,
      zIndex: 13,
    },
    district: {
      color: '#a9dff4',
      width: 1,
      lineDash: [5, 4],
      fill: plotCount > 0 && resolution < 1800
        ? 'rgba(56, 139, 91, 0.032)'
        : 'rgba(45, 132, 194, 0.004)',
      font: '9px sans-serif',
      showLabel: plotCount > 0 && resolution < 2800,
      zIndex: 12,
    },
  }[level] || {
    color: '#a9dff4',
    width: 1,
    lineDash: [5, 4],
    fill: 'rgba(45, 132, 194, 0.004)',
    font: '10px sans-serif',
    showLabel: resolution < 220,
    zIndex: 12,
  }
  const lineStyle = new Style({
    fill: new Fill({ color: styleConfig.fill }),
    stroke: new Stroke({
      color: styleConfig.color,
      width: styleConfig.width,
      lineDash: styleConfig.lineDash,
    }),
    zIndex: styleConfig.zIndex,
  })
  if (!styleConfig.showLabel) return lineStyle
  const geometry = feature.getGeometry()
  if (!geometry) return lineStyle
  const labelStyle = new Style({
    // MultiPolygon 默认会在每个组成面重复标注，统一使用整体范围中心只显示一次。
    geometry: new Point(getCenter(geometry.getExtent())),
    text: new Text({
      text: level === 'district'
        ? `${boundaryName}\n${plotCount} 块`
        : `${boundaryName}${level === 'province' ? '' : `\n${plotCount} 小地块`}`,
      font: styleConfig.font,
      fill: new Fill({ color: level === 'district' ? '#28583f' : '#f2fbff' }),
      stroke: new Stroke({
        color: level === 'district' ? 'rgba(255, 255, 255, 0.96)' : '#17455d',
        width: level === 'district' ? 2 : 3,
      }),
      backgroundFill: new Fill({
        color: level === 'district'
          ? 'rgba(255, 255, 255, 0.78)'
          : 'rgba(21, 62, 49, 0.72)',
      }),
      padding: level === 'district' ? [1, 3, 1, 3] : [2, 4, 2, 4],
      overflow: true,
    }),
    zIndex: styleConfig.zIndex + 1,
  })
  return [lineStyle, labelStyle]
}

const refreshFeatures = (): void => {
  if (!farmlandLayer) return
  const source = farmlandLayer.getSource()
  source?.clear()
  if (!layerStore.farmlandFeaturesRef?.features?.length) return

  // 后端 API 的 GeoJSON 均为 WGS84，OpenLayers 显式投影到 Web Mercator。
  const features = new GeoJSON().readFeatures(layerStore.farmlandFeaturesRef, {
    dataProjection: 'EPSG:4326',
    featureProjection: 'EPSG:3857',
  })
  source?.addFeatures(features)
}

const refreshFieldFeatures = (): void => {
  if (!fieldLayer) return
  const source = fieldLayer.getSource()
  source?.clear()
  if (!layerStore.fieldFeaturesRef?.features?.length) return
  const features = new GeoJSON().readFeatures(layerStore.fieldFeaturesRef, {
    dataProjection: 'EPSG:4326',
    featureProjection: 'EPSG:3857',
  })
  source?.addFeatures(features)
}

const refreshDisasterFeatures = (): void => {
  if (!disasterLayer) return
  const source = disasterLayer.getSource()
  source?.clear()
  if (!layerStore.disasterFeaturesRef?.features?.length) return
  const features = new GeoJSON().readFeatures(layerStore.disasterFeaturesRef, {
    dataProjection: 'EPSG:4326',
    featureProjection: 'EPSG:3857',
  })
  source?.addFeatures(features)
}

const refreshBoundaryFeatures = (): void => {
  if (!boundaryLayer) return
  const source = boundaryLayer.getSource()
  source?.clear()
  if (!layerStore.boundaryFeaturesRef?.features?.length) return
  const features = new GeoJSON().readFeatures(layerStore.boundaryFeaturesRef, {
    dataProjection: 'EPSG:4326',
    featureProjection: 'EPSG:3857',
  })
  const plotCounts = new globalThis.Map<string, number>()
  const province = layerStore.farmlandHierarchyComputed[0]
  province?.children?.forEach((city) => {
    plotCounts.set(city.key.split(':')[1] || '', city.count)
    city.children?.forEach((district) => {
      plotCounts.set(district.key.split(':')[1] || '', district.count)
    })
  })
  features.forEach((feature) => {
    const boundaryCode = String(feature.get('boundary_code') || '')
    feature.set('plot_count', plotCounts.get(boundaryCode) || 0, true)
  })
  source?.addFeatures(features)
}

const updateLayerState = (): void => {
  if (!baseLayer || !farmlandLayer || !disasterLayer || !boundaryLayer || !fieldLayer) return
  const base = layerStore.layersRef.find((layer) => layer.key === 'base')
  const farmland = layerStore.layersRef.find((layer) => layer.key === 'farmland')
  const disaster = layerStore.layersRef.find((layer) => layer.key === 'disaster')
  const boundary = layerStore.layersRef.find((layer) => layer.key === 'boundary')
  const field = layerStore.layersRef.find((layer) => layer.key === 'field')
  baseLayer.setVisible(base?.visible ?? true)
  baseLayer.setOpacity((base?.opacity ?? 100) / 100)
  farmlandLayer.setVisible(farmland?.visible ?? true)
  farmlandLayer.setOpacity((farmland?.opacity ?? 100) / 100)
  disasterLayer.setVisible(disaster?.visible ?? false)
  disasterLayer.setOpacity((disaster?.opacity ?? 100) / 100)
  boundaryLayer.setVisible(boundary?.visible ?? true)
  boundaryLayer.setOpacity((boundary?.opacity ?? 100) / 100)
  fieldLayer.setVisible(field?.visible ?? true)
}

const initializeMap = (): void => {
  baseLayer = new TileLayer({
    source: new XYZ({
      attributions: [],
      crossOrigin: 'anonymous',
      url: '/imagery-tiles/{z}/{y}/{x}',
    }),
  })
  farmlandLayer = new VectorLayer({
    source: new VectorSource(),
    style: (feature) => {
      const plotCode = String(feature.get('plot_code') || '')
      if (plotCode === mapStore.selectedPlotRef?.plot_code) return selectedStyle
      if (workbenchStore.mergeSelectionCodesComputed.includes(plotCode)) {
        return mergeSelectedStyle
      }
      return farmlandStyle(feature)
    },
  })
  disasterLayer = new VectorLayer({
    source: new VectorSource(),
    style: disasterStyle,
    zIndex: 15,
  })
  boundaryLayer = new VectorLayer({
    source: new VectorSource(),
    style: boundaryStyle,
    declutter: true,
    zIndex: 12,
  })
  fieldLayer = new VectorLayer({
    source: new VectorSource(),
    style: fieldStyle,
    zIndex: 20,
  })
  drawLayer = new VectorLayer({
    source: new VectorSource(),
    style: new Style({
      fill: new Fill({ color: 'rgba(33, 118, 78, 0.13)' }),
      stroke: new Stroke({ color: '#167047', width: 2, lineDash: [8, 5] }),
    }),
  })

  map = new Map({
    target: targetRef.value ?? undefined,
    layers: [
      baseLayer,
      farmlandLayer,
      boundaryLayer,
      disasterLayer,
      fieldLayer,
      drawLayer,
    ],
    view: new View({
      center: fromLonLat(mapStore.centerRef),
      zoom: mapStore.zoomRef,
      minZoom: 3,
      maxZoom: 20,
    }),
  })

  map.on('moveend', () => {
    if (syncingView || mapStore.viewTypeRef !== '2d') return
    const view = map?.getView()
    if (!view) return
    const center = toLonLat(view.getCenter() || [0, 0])
    mapStore.updateView(
      [center[0] ?? 0, center[1] ?? 0],
      view.getZoom() ?? mapStore.zoomRef,
    )
    loadVisiblePlots()
  })

  map.on('singleclick', (event) => {
    if (
      drawInteraction
      || modifyInteraction
      || Date.now() < suppressClickUntil
    ) return
    const [lon, lat] = toLonLat(event.coordinate)
    emit('coordinate-picked', { lon, lat })
  })

  refreshFeatures()
  refreshDisasterFeatures()
  refreshBoundaryFeatures()
  refreshFieldFeatures()
  updateLayerState()
  loadVisiblePlots()
}

const serializePolygon = (geometry: Geometry): PolygonGeometry | null => {
  const serialized = new GeoJSON().writeGeometryObject(geometry, {
    dataProjection: 'EPSG:4326',
    featureProjection: 'EPSG:3857',
  })
  if (serialized.type !== 'Polygon') return null
  return serialized as unknown as PolygonGeometry
}

const serializeLineString = (geometry: Geometry): LineStringGeometry | null => {
  const serialized = new GeoJSON().writeGeometryObject(geometry, {
    dataProjection: 'EPSG:4326',
    featureProjection: 'EPSG:3857',
  })
  if (serialized.type !== 'LineString') return null
  return serialized as unknown as LineStringGeometry
}

const removeModifyInteraction = (): void => {
  if (map && modifyInteraction) map.removeInteraction(modifyInteraction)
  modifyInteraction = null
}

const startPolygonDraw = (): boolean => {
  if (!map || !drawLayer?.getSource()) return false
  clearEditing()
  refreshFeatures()
  drawInteraction = new Draw({
    source: drawLayer.getSource() ?? undefined,
    type: 'Polygon',
  })
  map.addInteraction(drawInteraction)
  drawInteraction.once('drawend', (event: DrawEvent) => {
    suppressClickUntil = Date.now() + 500
    const geometry = event.feature.getGeometry()
    const polygon = geometry ? serializePolygon(geometry) : null
    if (polygon) emit('geometry-drawn', polygon)
    if (map && drawInteraction) map.removeInteraction(drawInteraction)
    drawInteraction = null
  })
  return true
}

const startVertexEdit = (): boolean => {
  if (!map || !farmlandLayer) return false
  const plotCode = mapStore.selectedPlotRef?.plot_code
  if (!plotCode) return false
  clearEditing()
  refreshFeatures()
  const feature = farmlandLayer.getSource()?.getFeatures().find(
    (item) => item.get('plot_code') === plotCode,
  )
  if (!feature) return false
  modifyInteraction = new Modify({
    features: new Collection([feature]),
  })
  map.addInteraction(modifyInteraction)
  modifyInteraction.once('modifyend', (event: ModifyEvent) => {
    suppressClickUntil = Date.now() + 500
    const geometry = event.features.item(0)?.getGeometry()
    const polygon = geometry ? serializePolygon(geometry) : null
    removeModifyInteraction()
    if (polygon) emit('geometry-modified', polygon)
  })
  return true
}

const startSplitLineDraw = (): boolean => {
  if (!map || !drawLayer?.getSource()) return false
  if (!mapStore.selectedPlotRef?.plot_code) return false
  clearEditing()
  refreshFeatures()
  drawInteraction = new Draw({
    source: drawLayer.getSource() ?? undefined,
    type: 'LineString',
  })
  map.addInteraction(drawInteraction)
  drawInteraction.once('drawend', (event: DrawEvent) => {
    suppressClickUntil = Date.now() + 500
    const geometry = event.feature.getGeometry()
    const line = geometry ? serializeLineString(geometry) : null
    if (map && drawInteraction) map.removeInteraction(drawInteraction)
    drawInteraction = null
    if (line) emit('split-line-drawn', line)
  })
  return true
}

const clearEditing = (): void => {
  if (map && drawInteraction) map.removeInteraction(drawInteraction)
  drawInteraction = null
  removeModifyInteraction()
  drawLayer?.getSource()?.clear()
}

const restoreFeatures = (): void => {
  removeModifyInteraction()
  refreshFeatures()
}

const flyToFeature = (feature: GeoJsonFeature): void => {
  if (!map || !feature) return
  const features = new GeoJSON().readFeatures(feature, {
    dataProjection: 'EPSG:4326',
    featureProjection: 'EPSG:3857',
  })
  if (!features.length) return
  const extent = features.reduce(
    (combinedExtent, item) => {
      const geometry = item.getGeometry()
      return geometry ? extend(combinedExtent, geometry.getExtent()) : combinedExtent
    },
    createEmpty(),
  )
  map.getView().fit(extent, {
    padding: [70, 70, 70, 70],
    duration: 650,
    maxZoom: 16,
  })
}

watch(
  () => layerStore.farmlandFeaturesRef,
  () => {
    refreshFeatures()
    refreshBoundaryFeatures()
  },
  { deep: true },
)

watch(
  () => layerStore.fieldFeaturesRef,
  refreshFieldFeatures,
  { deep: true },
)

watch(
  () => layerStore.disasterFeaturesRef,
  refreshDisasterFeatures,
  { deep: true },
)

watch(
  () => layerStore.boundaryFeaturesRef,
  refreshBoundaryFeatures,
  { deep: true },
)

watch(
  () => layerStore.layersRef,
  updateLayerState,
  { deep: true },
)

watch(
  () => workbenchStore.mergeSelectionCodesComputed.join(','),
  () => farmlandLayer?.changed(),
)

watch(
  () => mapStore.selectedPlotRef,
  () => farmlandLayer?.changed(),
  { deep: true },
)

watch(
  () => mapStore.focusRequestRef,
  (request) => {
    if (!request || !map || mapStore.viewTypeRef !== '2d') return
    const extent = transformExtent(
      request.extent,
      'EPSG:4326',
      'EPSG:3857',
    )
    // 仅响应用户点击行政层级，不使用动画，避免产生自动移动观感。
    map.getView().fit(extent, {
      padding: [80, 80, 80, 80],
      duration: 0,
      maxZoom: 15,
    })
  },
  { deep: true },
)

watch(
  () => mapStore.viewTypeRef,
  (viewType) => {
    if (viewType !== '2d' || !map) return
    syncingView = true
    map.updateSize()
    map.getView().setCenter(fromLonLat(mapStore.centerRef))
    map.getView().setZoom(mapStore.zoomRef)
    requestAnimationFrame(() => {
      syncingView = false
      loadVisiblePlots()
    })
  },
)

onMounted(initializeMap)

onBeforeUnmount(() => {
  clearEditing()
  map?.setTarget(undefined)
  map = null
})

defineExpose({
  map,
  startPolygonDraw,
  startVertexEdit,
  startSplitLineDraw,
  clearEditing,
  restoreFeatures,
  flyToFeature,
})
</script>

<template>
  <div ref="targetRef" class="ol-map" />
</template>

<style scoped>
.ol-map {
  width: 100%;
  height: 100%;
}

:deep(.ol-zoom) {
  top: 14px;
  left: 14px;
}

:deep(.ol-control) {
  padding: 0;
  background: transparent;
}

:deep(.ol-control button) {
  width: 32px;
  height: 32px;
  margin: 0 0 4px;
  font-size: 18px;
  line-height: 30px;
  color: #fff;
  background-color: rgb(20 82 56 / 88%);
  border-radius: 5px;
  box-shadow: 0 2px 8px rgb(12 51 35 / 20%);
}

:deep(.ol-control button:hover),
:deep(.ol-control button:focus) {
  background-color: #176647;
}

:deep(.ol-attribution) {
  display: none;
}
</style>
