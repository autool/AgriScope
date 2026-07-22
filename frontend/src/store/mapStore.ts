import { defineStore } from 'pinia'
import { ref } from 'vue'

import type { GeoJsonFeature, PlotProperties } from '@/types/workbench'

export type MapViewType = '2d' | '3d'
export type MapCenter = [number, number]
export type MapExtent = [number, number, number, number]
export type SelectedPlot = PlotProperties & {
  feature?: GeoJsonFeature<PlotProperties>
}

export interface MapFocusRequest {
  extent: MapExtent
  requestId: number
}

export const useMapStore = defineStore('map', () => {
  const viewTypeRef = ref<MapViewType>('2d')
  const centerRef = ref<MapCenter>([127.6, 47.7])
  const zoomRef = ref<number>(5.5)
  const selectedPlotRef = ref<SelectedPlot | null>(null)
  const focusRequestRef = ref<MapFocusRequest | null>(null)

  const setViewType = (type: MapViewType): void => {
    viewTypeRef.value = type
  }

  const toggleViewType = (): void => {
    viewTypeRef.value = viewTypeRef.value === '2d' ? '3d' : '2d'
  }

  const updateView = (nextCenter: MapCenter, nextZoom: number): void => {
    centerRef.value = [...nextCenter]
    zoomRef.value = nextZoom
  }

  const selectPlot = (plot: SelectedPlot): void => {
    selectedPlotRef.value = plot
  }

  const clearSelection = (): void => {
    selectedPlotRef.value = null
  }

  const focusExtent = (extent: MapExtent): void => {
    focusRequestRef.value = {
      extent: [...extent],
      requestId: (focusRequestRef.value?.requestId || 0) + 1,
    }
  }

  return {
    viewTypeRef,
    centerRef,
    zoomRef,
    selectedPlotRef,
    focusRequestRef,
    setViewType,
    toggleViewType,
    updateView,
    selectPlot,
    clearSelection,
    focusExtent,
  }
})
