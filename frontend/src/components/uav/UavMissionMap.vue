<script setup lang="ts">
import Feature from 'ol/Feature.js'
import type { FeatureLike } from 'ol/Feature.js'
import GeoJSON from 'ol/format/GeoJSON.js'
import type Geometry from 'ol/geom/Geometry.js'
import Point from 'ol/geom/Point.js'
import Polygon from 'ol/geom/Polygon.js'
import Draw from 'ol/interaction/Draw.js'
import type { DrawEvent } from 'ol/interaction/Draw.js'
import VectorLayer from 'ol/layer/Vector.js'
import TileLayer from 'ol/layer/Tile.js'
import Map from 'ol/Map.js'
import { fromLonLat, toLonLat } from 'ol/proj.js'
import VectorSource from 'ol/source/Vector.js'
import XYZ from 'ol/source/XYZ.js'
import { Circle as CircleStyle, Fill, Stroke, Style } from 'ol/style.js'
import View from 'ol/View.js'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { useLayerStore } from '@/store/layerStore'
import { useMapStore } from '@/store/mapStore'
import type { UavFinding, UavMission, UavPolygon } from '@/types/uav'

type InteractionMode = 'browse' | 'draw_boundary' | 'pick_finding'
type OlFeature = Feature<Geometry>
type OlVectorLayer = VectorLayer<VectorSource<OlFeature>>

const props = defineProps<{
  missions: UavMission[]
  findings: UavFinding[]
  selectedMissionCode: string | null
  draftBoundary: UavPolygon | null
  pickedCoordinate: { lon: number; lat: number } | null
  canPlan: boolean
  canRegisterFinding: boolean
}>()

const emit = defineEmits<{
  'select-mission': [missionCode: string]
  'boundary-drawn': [boundary: UavPolygon]
  'boundary-cleared': []
  'finding-coordinate-picked': [coordinate: { lon: number; lat: number }]
  'finding-coordinate-cleared': []
}>()

const layerStore = useLayerStore()
const mapStore = useMapStore()
const targetRef = ref<HTMLDivElement | null>(null)
const modeRef = ref<InteractionMode>('browse')

let map: Map | null = null
let boundaryLayer: OlVectorLayer | null = null
let missionLayer: OlVectorLayer | null = null
let findingLayer: OlVectorLayer | null = null
let draftLayer: OlVectorLayer | null = null
let drawInteraction: Draw | null = null
let syncingView = false

const baseLayer = new TileLayer({
  source: new XYZ({
    attributions: [],
    crossOrigin: 'anonymous',
    url: '/imagery-tiles/{z}/{y}/{x}',
  }),
})

const boundaryStyle = (feature: FeatureLike): Style => {
  const level = String(feature.get('boundary_level'))
  const config = {
    province: { color: '#2f9ed0', width: 3, dash: undefined },
    city: { color: '#67bce2', width: 1.8, dash: [9, 4] },
    district: { color: '#b1def0', width: 1, dash: [5, 4] },
  }[level] || { color: '#b1def0', width: 1, dash: [5, 4] }
  return new Style({
    fill: new Fill({ color: 'rgba(33, 109, 78, 0.018)' }),
    stroke: new Stroke({
      color: config.color,
      width: config.width,
      lineDash: config.dash,
    }),
    zIndex: level === 'province' ? 13 : level === 'city' ? 12 : 11,
  })
}

const missionStyle = (feature: FeatureLike): Style => {
  const selected = feature.get('mission_code') === props.selectedMissionCode
  return new Style({
    fill: new Fill({
      color: selected ? 'rgba(236, 144, 52, 0.28)' : 'rgba(71, 145, 103, 0.18)',
    }),
    stroke: new Stroke({
      color: selected ? '#e5872f' : '#3f9969',
      width: selected ? 3 : 2,
      lineDash: selected ? undefined : [7, 4],
    }),
    zIndex: selected ? 24 : 22,
  })
}

const findingStyle = (feature: FeatureLike): Style => {
  const status = String(feature.get('status'))
  const color = status === 'confirmed'
    ? '#d84a42'
    : status === 'dismissed'
      ? '#7d8b84'
      : '#e99a35'
  return new Style({
    image: new CircleStyle({
      radius: 6,
      fill: new Fill({ color }),
      stroke: new Stroke({ color: '#fff', width: 2 }),
    }),
    zIndex: 28,
  })
}

const draftStyle = (feature: FeatureLike): Style => {
  if (feature.getGeometry() instanceof Point) {
    return new Style({
      image: new CircleStyle({
        radius: 7,
        fill: new Fill({ color: '#7b54c6' }),
        stroke: new Stroke({ color: '#fff', width: 2 }),
      }),
      zIndex: 32,
    })
  }
  return new Style({
    fill: new Fill({ color: 'rgba(123, 84, 198, 0.22)' }),
    stroke: new Stroke({ color: '#7b54c6', width: 3, lineDash: [8, 4] }),
    zIndex: 30,
  })
}

const refreshBoundaries = (): void => {
  const source = boundaryLayer?.getSource()
  source?.clear()
  if (!layerStore.boundaryFeaturesRef.features.length) return
  source?.addFeatures(new GeoJSON().readFeatures(layerStore.boundaryFeaturesRef, {
    dataProjection: 'EPSG:4326',
    featureProjection: 'EPSG:3857',
  }) as OlFeature[])
}

const refreshMissions = (): void => {
  const source = missionLayer?.getSource()
  source?.clear()
  if (!props.missions.length) return
  const features = new GeoJSON().readFeatures({
    type: 'FeatureCollection',
    features: props.missions.map((mission) => ({
      type: 'Feature',
      geometry: mission.flight_boundary,
      properties: {
        mission_code: mission.mission_code,
        mission_name: mission.mission_name,
        status: mission.status,
      },
    })),
  }, {
    dataProjection: 'EPSG:4326',
    featureProjection: 'EPSG:3857',
  }) as OlFeature[]
  source?.addFeatures(features)
  missionLayer?.changed()
}

const refreshFindings = (): void => {
  const source = findingLayer?.getSource()
  source?.clear()
  const findings = props.selectedMissionCode
    ? props.findings.filter((item) => item.mission_code === props.selectedMissionCode)
    : props.findings
  source?.addFeatures(findings.map((finding) => new Feature({
    geometry: new Point(fromLonLat([finding.longitude, finding.latitude])),
    finding_code: finding.finding_code,
    mission_code: finding.mission_code,
    status: finding.status,
  })))
}

const refreshDraft = (): void => {
  const source = draftLayer?.getSource()
  source?.clear()
  if (props.draftBoundary) {
    const geometry = new GeoJSON().readGeometry(props.draftBoundary, {
      dataProjection: 'EPSG:4326',
      featureProjection: 'EPSG:3857',
    })
    source?.addFeature(new Feature({ geometry, draft_type: 'boundary' }))
  }
  if (props.pickedCoordinate) {
    source?.addFeature(new Feature({
      geometry: new Point(fromLonLat([
        props.pickedCoordinate.lon,
        props.pickedCoordinate.lat,
      ])),
      draft_type: 'finding',
    }))
  }
}

const removeDrawInteraction = (): void => {
  if (map && drawInteraction) map.removeInteraction(drawInteraction)
  drawInteraction = null
}

const handleBoundaryDrawn = (event: DrawEvent): void => {
  const geometry = event.feature.getGeometry()
  if (!(geometry instanceof Polygon)) return
  const boundary = new GeoJSON().writeGeometryObject(geometry, {
    dataProjection: 'EPSG:4326',
    featureProjection: 'EPSG:3857',
    decimals: 7,
  }) as UavPolygon
  emit('boundary-drawn', boundary)
  modeRef.value = 'browse'
  removeDrawInteraction()
}

const setMode = (mode: InteractionMode): void => {
  removeDrawInteraction()
  modeRef.value = mode
  if (mode !== 'draw_boundary' || !map || !draftLayer) return
  drawInteraction = new Draw({
    source: draftLayer.getSource() || undefined,
    type: 'Polygon',
  })
  drawInteraction.on('drawstart', () => emit('boundary-cleared'))
  drawInteraction.on('drawend', handleBoundaryDrawn)
  map.addInteraction(drawInteraction)
}

const fitLayer = (layer: OlVectorLayer | null, maxZoom: number): void => {
  if (!map || !layer) return
  const extent = layer.getSource()?.getExtent()
  if (!extent || !extent.every(Number.isFinite)) return
  map.getView().fit(extent, {
    padding: [40, 40, 40, 40],
    duration: 0,
    maxZoom,
  })
}

const focusSelectedMission = (): void => {
  if (!map || !missionLayer || !props.selectedMissionCode) return
  const feature = missionLayer.getSource()?.getFeatures().find(
    (item) => item.get('mission_code') === props.selectedMissionCode,
  )
  const extent = feature?.getGeometry()?.getExtent()
  if (!extent) return
  map.getView().fit(extent, {
    padding: [55, 55, 55, 55],
    duration: 0,
    maxZoom: 16,
  })
}

const initializeMap = (): void => {
  if (!targetRef.value) return
  boundaryLayer = new VectorLayer({
    source: new VectorSource(),
    style: boundaryStyle,
  })
  missionLayer = new VectorLayer({
    source: new VectorSource(),
    style: missionStyle,
  })
  findingLayer = new VectorLayer({
    source: new VectorSource(),
    style: findingStyle,
  })
  draftLayer = new VectorLayer({
    source: new VectorSource(),
    style: draftStyle,
  })
  map = new Map({
    target: targetRef.value,
    layers: [baseLayer, boundaryLayer, missionLayer, findingLayer, draftLayer],
    view: new View({
      center: fromLonLat(mapStore.centerRef),
      zoom: mapStore.zoomRef,
      minZoom: 4,
      maxZoom: 19,
    }),
  })
  map.on('moveend', () => {
    if (!map || syncingView) return
    const center = toLonLat(map.getView().getCenter() || fromLonLat(mapStore.centerRef))
    mapStore.updateView(
      [Number(center[0].toFixed(7)), Number(center[1].toFixed(7))],
      map.getView().getZoom() ?? mapStore.zoomRef,
    )
  })
  map.on('singleclick', (event) => {
    if (!map) return
    if (modeRef.value === 'pick_finding') {
      const coordinate = toLonLat(event.coordinate)
      emit('finding-coordinate-picked', {
        lon: Number(coordinate[0].toFixed(7)),
        lat: Number(coordinate[1].toFixed(7)),
      })
      modeRef.value = 'browse'
      return
    }
    if (modeRef.value !== 'browse') return
    const feature = map.forEachFeatureAtPixel(event.pixel, (candidate) => candidate, {
      layerFilter: (layer) => layer === missionLayer,
    })
    const missionCode = feature?.get('mission_code')
    if (missionCode) emit('select-mission', String(missionCode))
  })
  refreshBoundaries()
  refreshMissions()
  refreshFindings()
  refreshDraft()
  window.setTimeout(() => {
    map?.updateSize()
    if (props.selectedMissionCode) focusSelectedMission()
    else fitLayer(boundaryLayer, 7)
  })
}

watch(() => layerStore.boundaryFeaturesRef, refreshBoundaries, { deep: true })
watch(() => props.missions, refreshMissions, { deep: true })
watch(() => props.findings, refreshFindings, { deep: true })
watch(() => props.selectedMissionCode, () => {
  missionLayer?.changed()
  refreshFindings()
  focusSelectedMission()
})
watch(() => [props.draftBoundary, props.pickedCoordinate], refreshDraft, { deep: true })
watch(() => [mapStore.centerRef, mapStore.zoomRef], () => {
  if (!map) return
  syncingView = true
  map.getView().setCenter(fromLonLat(mapStore.centerRef))
  map.getView().setZoom(mapStore.zoomRef)
  window.setTimeout(() => { syncingView = false })
}, { deep: true })

onMounted(initializeMap)
onBeforeUnmount(() => {
  removeDrawInteraction()
  map?.setTarget(undefined)
  map = null
})
</script>

<template>
  <section class="uav-map-panel">
    <header>
      <div>
        <small>SPATIAL PLANNING</small>
        <h3>飞行范围与疑点空间工作台</h3>
      </div>
      <a-space size="small">
        <a-button
          size="small"
          :type="modeRef === 'draw_boundary' ? 'primary' : 'default'"
          :disabled="!canPlan"
          @click="setMode('draw_boundary')"
        >
          绘制飞行范围
        </a-button>
        <a-button
          size="small"
          :type="modeRef === 'pick_finding' ? 'primary' : 'default'"
          :disabled="!canRegisterFinding || !selectedMissionCode"
          @click="setMode('pick_finding')"
        >
          拾取疑点坐标
        </a-button>
      </a-space>
    </header>
    <div class="map-toolbar">
      <span :class="`mode-${modeRef}`">
        {{ modeRef === 'draw_boundary' ? '在地图逐点绘制闭合 Polygon' : modeRef === 'pick_finding' ? '点击任务范围内疑点位置' : '点击已有任务可切换当前任务' }}
      </span>
      <a-space size="small">
        <a-button size="small" @click="fitLayer(boundaryLayer, 7)">全省</a-button>
        <a-button size="small" :disabled="!selectedMissionCode" @click="focusSelectedMission">当前任务</a-button>
        <a-button v-if="draftBoundary" size="small" @click="emit('boundary-cleared')">清除范围草稿</a-button>
        <a-button v-if="pickedCoordinate" size="small" @click="emit('finding-coordinate-cleared')">清除疑点草稿</a-button>
      </a-space>
    </div>
    <div ref="targetRef" class="map-target" />
    <footer>
      <span><i class="mission" />飞行任务</span>
      <span><i class="draft" />待提交草稿</span>
      <span><i class="pending" />待复核疑点</span>
      <em>底图：当前公开/业务影像瓦片 · API 几何 EPSG:4326</em>
    </footer>
  </section>
</template>

<style scoped>
.uav-map-panel { display: grid; grid-template-rows: auto auto minmax(0, 1fr) auto; min-height: 0; padding: 10px; overflow: hidden; background: #fff; border: 1px solid #dfe5e2; border-radius: 8px; }
header, .map-toolbar, footer { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
header { margin-bottom: 7px; }
small { font-size: 8px; color: #718078; letter-spacing: 1px; }
h3 { margin: 2px 0 0; font-size: 15px; color: #20352c; }
.map-toolbar { min-height: 31px; padding: 4px 6px; margin-bottom: 6px; font-size: 9px; color: #64746c; background: #f5f8f6; border: 1px solid #e2e8e5; border-radius: 5px; }
.map-toolbar > span { padding-left: 7px; border-left: 3px solid #7f9288; }
.map-toolbar .mode-draw_boundary { color: #6741a4; border-color: #7b54c6; }
.map-toolbar .mode-pick_finding { color: #9a5d17; border-color: #e99a35; }
.map-target { min-height: 0; background: #dfe7e2; border: 1px solid #d4ddd8; border-radius: 6px; }
footer { flex-wrap: wrap; padding-top: 6px; font-size: 8px; color: #718078; }
footer span { display: inline-flex; gap: 4px; align-items: center; }
footer i { width: 14px; height: 7px; border: 2px solid; border-radius: 2px; }
footer i.mission { background: rgb(71 145 103 / 18%); border-color: #3f9969; }
footer i.draft { background: rgb(123 84 198 / 22%); border-color: #7b54c6; border-style: dashed; }
footer i.pending { width: 8px; height: 8px; background: #e99a35; border-color: #fff; border-radius: 50%; }
footer em { margin-left: auto; font-style: normal; }
:deep(.ol-zoom) { top: 8px; left: 8px; }
:deep(.ol-control button) { color: #345848; background: rgb(255 255 255 / 92%); }
:deep(.ol-attribution) { display: none; }
</style>
