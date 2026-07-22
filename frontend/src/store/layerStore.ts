import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import type {
  BoundaryProperties,
  GeoJsonFeature,
  GeoJsonFeatureCollection,
  PlotCatalog,
  PlotProperties,
} from '@/types/workbench'
import type { MapExtent } from '@/store/mapStore'
import { getGeoJsonFeatureExtent } from '@/utils/geojson'

export interface LayerDefinition {
  key: string
  title: string
  visible: boolean
  opacity: number
  type: 'raster' | 'vector' | 'point' | 'line'
}

export interface FarmlandHierarchyNode {
  key: string
  title: string
  level: 'province' | 'city' | 'district' | 'plot'
  count: number
  extent: MapExtent
  plotCode?: string
  landClass?: string | null
  children?: FarmlandHierarchyNode[]
}

interface MutableRegionGroup {
  code: string
  name: string
  extent: MapExtent
  count: number
  districts: Map<string, MutableRegionGroup>
  plots: FarmlandHierarchyNode[]
}

const emptyFeatureCollection = <
  TProperties extends Record<string, unknown> = Record<string, unknown>,
>(): GeoJsonFeatureCollection<TProperties> => ({
  type: 'FeatureCollection',
  features: [],
})

const createRegionGroup = (
  code: string,
  name: string,
  extent: MapExtent,
): MutableRegionGroup => ({
  code,
  name,
  extent,
  count: 0,
  districts: new Map(),
  plots: [],
})

const getPlotNodeTitle = (
  plotCode: string,
  sourceFeatureId: string | null,
): string => {
  const sourceId = sourceFeatureId || ''
  if (sourceId.startsWith('way/')) {
    return `地块 ${sourceId.slice('way/'.length)}`
  }
  if (sourceId.startsWith('relation/')) {
    return `组合地块 ${sourceId.slice('relation/'.length).replace('#part/', ' · 分片 ')}`
  }
  return plotCode
}

export const useLayerStore = defineStore('layer', () => {
  const layersRef = ref<LayerDefinition[]>([
    { key: 'base', title: '卫星影像 · 默认底图', visible: true, opacity: 100, type: 'raster' },
    { key: 'farmland', title: '地块解译成果', visible: true, opacity: 76, type: 'vector' },
    { key: 'disaster', title: '灾害识别斑块', visible: false, opacity: 65, type: 'vector' },
    { key: 'field', title: '外业核查点', visible: true, opacity: 100, type: 'point' },
    { key: 'boundary', title: '行政区划界线 · 省市县', visible: true, opacity: 72, type: 'line' },
  ])
  const farmlandFeaturesRef = ref<GeoJsonFeatureCollection<PlotProperties>>(
    emptyFeatureCollection<PlotProperties>(),
  )
  const plotCatalogRef = ref<PlotCatalog | null>(null)
  const fieldFeaturesRef = ref<GeoJsonFeatureCollection>(emptyFeatureCollection())
  const disasterFeaturesRef = ref<GeoJsonFeatureCollection>(emptyFeatureCollection())
  const boundaryFeaturesRef = ref<GeoJsonFeatureCollection<BoundaryProperties>>(
    emptyFeatureCollection<BoundaryProperties>(),
  )

  const administrativeHierarchyComputed = computed<FarmlandHierarchyNode[]>(() => {
    const provinceFeature = boundaryFeaturesRef.value.features.find(
      (feature) => feature.properties.boundary_level === 'province',
    )
    const provinceExtent = provinceFeature
      ? getGeoJsonFeatureExtent(provinceFeature)
      : null
    if (!provinceFeature || !provinceExtent) return []
    const cities = new Map<string, MutableRegionGroup>()
    boundaryFeaturesRef.value.features
      .filter((feature) => feature.properties.boundary_level === 'city')
      .forEach((feature) => {
        const extent = getGeoJsonFeatureExtent(feature)
        if (!extent) return
        cities.set(
          feature.properties.boundary_code,
          createRegionGroup(
            feature.properties.boundary_code,
            feature.properties.boundary_name,
            extent,
          ),
        )
      })
    boundaryFeaturesRef.value.features
      .filter((feature) => feature.properties.boundary_level === 'district')
      .forEach((feature) => {
        const extent = getGeoJsonFeatureExtent(feature)
        if (!extent) return
        const city = cities.get(feature.properties.parent_code || '')
        if (!city) return
        city.districts.set(
          feature.properties.boundary_code,
          createRegionGroup(
            feature.properties.boundary_code,
            feature.properties.boundary_name,
            extent,
          ),
        )
      })
    return [{
      key: `boundary-province:${provinceFeature.properties.boundary_code}`,
      title: provinceFeature.properties.boundary_name,
      level: 'province',
      count: cities.size,
      extent: provinceExtent,
      children: [...cities.values()]
        .sort((left, right) => left.name.localeCompare(right.name, 'zh-CN'))
        .map((city) => ({
          key: `boundary-city:${city.code}`,
          title: city.name,
          level: 'city',
          count: city.districts.size,
          extent: city.extent,
          children: [...city.districts.values()]
            .sort((left, right) => left.name.localeCompare(right.name, 'zh-CN'))
            .map((district) => ({
              key: `boundary-district:${district.code}`,
              title: district.name,
              level: 'district',
              count: 0,
              extent: district.extent,
            })),
        })),
    }]
  })

  const farmlandHierarchyComputed = computed<FarmlandHierarchyNode[]>(() => {
    const cities = new Map<string, MutableRegionGroup>()
    const provinceNode = administrativeHierarchyComputed.value[0]
    if (!provinceNode) return []
    provinceNode.children?.forEach((cityNode) => {
      const city = createRegionGroup(cityNode.key.split(':')[1], cityNode.title, cityNode.extent)
      cityNode.children?.forEach((districtNode) => {
        const districtCode = districtNode.key.split(':')[1]
        city.districts.set(
          districtCode,
          createRegionGroup(districtCode, districtNode.title, districtNode.extent),
        )
      })
      cities.set(city.code, city)
    })
    const districtIndex = new Map<string, {
      city: MutableRegionGroup
      district: MutableRegionGroup
    }>()
    cities.forEach((city) => {
      city.districts.forEach((district, districtCode) => {
        districtIndex.set(districtCode, { city, district })
      })
    })
    plotCatalogRef.value?.districts.forEach((catalogDistrict) => {
      const matched = districtIndex.get(catalogDistrict.district_code)
      if (!matched) return
      const { city, district } = matched
      city.count += catalogDistrict.plot_count
      district.count = catalogDistrict.plot_count
      district.plots = catalogDistrict.plots.map((plot) => ({
        key: `farmland-plot:${plot.plot_code}`,
        title: getPlotNodeTitle(plot.plot_code, plot.source_feature_id),
        level: 'plot',
        count: 1,
        extent: [...plot.extent] as MapExtent,
        plotCode: plot.plot_code,
        landClass: plot.land_class,
      }))
    })
    const cityNodes = [...cities.values()]
      .sort((left, right) => left.name.localeCompare(right.name, 'zh-CN'))
      .map<FarmlandHierarchyNode>((city) => ({
        key: `farmland-city:${city.code}`,
        title: city.name,
        level: 'city',
        count: city.count,
        extent: city.extent,
        children: [...city.districts.values()]
          .sort((left, right) => left.name.localeCompare(right.name, 'zh-CN'))
          .map((district) => ({
            key: `farmland-district:${district.code}`,
            title: district.name,
            level: 'district',
            count: district.count,
            extent: district.extent,
            children: district.plots.sort((left, right) => left.title.localeCompare(right.title)),
          })),
      }))
    return [{
      key: 'farmland-province:230000',
      title: '黑龙江省',
      level: 'province',
      count: plotCatalogRef.value?.total_count || 0,
      extent: provinceNode.extent,
      children: cityNodes,
    }]
  })

  const setVisibility = (key: string, visible: boolean): void => {
    const layer = layersRef.value.find((item) => item.key === key)
    if (layer) layer.visible = visible
  }

  const setOpacity = (key: string, opacity: number): void => {
    const layer = layersRef.value.find((item) => item.key === key)
    if (layer) layer.opacity = opacity
  }

  const setFarmlandFeatures = (
    geojson: GeoJsonFeatureCollection<PlotProperties> | GeoJsonFeature<PlotProperties>,
  ): void => {
    farmlandFeaturesRef.value = geojson?.type === 'Feature'
      ? { type: 'FeatureCollection', features: [geojson] }
      : geojson || emptyFeatureCollection()
  }

  const setPlotCatalog = (catalog: PlotCatalog | null): void => {
    plotCatalogRef.value = catalog
  }

  const clearFeatures = () => {
    farmlandFeaturesRef.value = emptyFeatureCollection()
    plotCatalogRef.value = null
    fieldFeaturesRef.value = emptyFeatureCollection()
    disasterFeaturesRef.value = emptyFeatureCollection()
    boundaryFeaturesRef.value = emptyFeatureCollection<BoundaryProperties>()
  }

  const setFieldFeatures = (geojson: GeoJsonFeatureCollection): void => {
    fieldFeaturesRef.value = geojson || emptyFeatureCollection()
  }

  const setDisasterFeatures = (geojson: GeoJsonFeatureCollection): void => {
    disasterFeaturesRef.value = geojson || emptyFeatureCollection()
  }

  const setBoundaryFeatures = (
    geojson: GeoJsonFeatureCollection<BoundaryProperties>,
  ): void => {
    boundaryFeaturesRef.value = geojson
      || emptyFeatureCollection<BoundaryProperties>()
  }

  return {
    layersRef,
    administrativeHierarchyComputed,
    farmlandHierarchyComputed,
    farmlandFeaturesRef,
    plotCatalogRef,
    fieldFeaturesRef,
    disasterFeaturesRef,
    boundaryFeaturesRef,
    setVisibility,
    setOpacity,
    setFarmlandFeatures,
    setPlotCatalog,
    setFieldFeatures,
    setDisasterFeatures,
    setBoundaryFeatures,
    clearFeatures,
  }
})
