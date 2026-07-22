<script setup lang="ts">
import type Feature from 'ol/Feature.js'
import type { FeatureLike } from 'ol/Feature.js'
import GeoJSON from 'ol/format/GeoJSON.js'
import type Geometry from 'ol/geom/Geometry.js'
import TileLayer from 'ol/layer/Tile.js'
import VectorLayer from 'ol/layer/Vector.js'
import Map from 'ol/Map.js'
import { fromLonLat, toLonLat } from 'ol/proj.js'
import VectorSource from 'ol/source/Vector.js'
import XYZ from 'ol/source/XYZ.js'
import { Fill, Stroke, Style } from 'ol/style.js'
import View from 'ol/View.js'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { useMapStore } from '@/store/mapStore'
import type { ChangeFeatureCollection } from '@/types/changeDetection'

type CandidateFeature = Feature<Geometry>

const props = defineProps<{
  featureCollection: ChangeFeatureCollection
  selectedCandidateCode: string
}>()

const emit = defineEmits<{
  'candidate-selected': [candidateCode: string]
}>()

const mapStore = useMapStore()
const targetRef = ref<HTMLDivElement | null>(null)
let map: Map | null = null
let candidateLayer: VectorLayer<VectorSource<CandidateFeature>> | null = null

const classColors: Record<string, string> = {
  unclassified: '#d4a13d',
  suspected_construction: '#e0573e',
  farmland_outflow: '#cf7a2a',
  construction_facility_change: '#9d5b43',
  non_farmland_agricultural_change: '#7864b7',
  unused_land_change: '#71828c',
  farmland_attribute_change: '#2f8c63',
}

const candidateStyle = (feature: FeatureLike): Style => {
  const code = String(feature.get('candidate_code') || '')
  const changeClass = String(feature.get('change_class') || '')
  const status = String(feature.get('status') || 'pending')
  const baseColor = classColors[changeClass] || '#d87b38'
  const selected = code === props.selectedCandidateCode
  const excluded = status === 'excluded'
  return new Style({
    fill: new Fill({
      color: excluded ? 'rgba(120, 128, 124, 0.14)' : `${baseColor}42`,
    }),
    stroke: new Stroke({
      color: selected ? '#e8ff64' : excluded ? '#7f8b85' : baseColor,
      width: selected ? 4 : 2.2,
      lineDash: excluded ? [7, 5] : undefined,
    }),
    zIndex: selected ? 30 : 20,
  })
}

const syncFeatures = (): void => {
  if (!candidateLayer) return
  const source = candidateLayer.getSource()
  source?.clear()
  const features = new GeoJSON().readFeatures(props.featureCollection, {
    dataProjection: 'EPSG:4326',
    featureProjection: 'EPSG:3857',
  }) as CandidateFeature[]
  source?.addFeatures(features)
}

const initializeMap = (): void => {
  candidateLayer = new VectorLayer({
    source: new VectorSource<CandidateFeature>(),
    style: candidateStyle,
    zIndex: 20,
  })
  map = new Map({
    target: targetRef.value ?? undefined,
    layers: [
      new TileLayer({
        source: new XYZ({
          attributions: [],
          crossOrigin: 'anonymous',
          url: '/imagery-tiles/{z}/{y}/{x}',
        }),
      }),
      candidateLayer,
    ],
    view: new View({
      center: fromLonLat(mapStore.centerRef),
      zoom: mapStore.zoomRef,
      minZoom: 3,
      maxZoom: 20,
    }),
  })
  map.on('moveend', () => {
    const view = map?.getView()
    if (!view) return
    const center = toLonLat(view.getCenter() || [0, 0])
    mapStore.updateView(
      [center[0] ?? 0, center[1] ?? 0],
      view.getZoom() ?? mapStore.zoomRef,
    )
  })
  map.on('singleclick', (event) => {
    const feature = map?.forEachFeatureAtPixel(
      event.pixel,
      (matched) => matched,
      { layerFilter: (layer) => layer === candidateLayer },
    )
    const candidateCode = String(feature?.get('candidate_code') || '')
    if (candidateCode) emit('candidate-selected', candidateCode)
  })
  syncFeatures()
}

watch(() => props.featureCollection, syncFeatures, { deep: true })
watch(
  () => props.selectedCandidateCode,
  () => candidateLayer?.changed(),
)

onMounted(initializeMap)
onBeforeUnmount(() => {
  map?.setTarget(undefined)
  map = null
  candidateLayer = null
})
</script>

<template>
  <div ref="targetRef" class="change-candidate-map" />
</template>

<style scoped>
.change-candidate-map { width: 100%; height: 100%; min-height: 360px; background: #dce5df; }
</style>
