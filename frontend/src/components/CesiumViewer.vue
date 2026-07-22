<script setup lang="ts">
import {
  Cartesian2,
  Cartesian3,
  Cesium3DTileset,
  Color,
  ColorMaterialProperty,
  ConstantProperty,
  GeoJsonDataSource,
  HeadingPitchRange,
  Matrix4,
  Math as CesiumMath,
  Rectangle,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  UrlTemplateImageryProvider,
  Viewer,
} from 'cesium'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { useLayerStore } from '@/store/layerStore'
import { useMapStore } from '@/store/mapStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type { GeoJsonFeature } from '@/types/workbench'
import { heightToZoom, zoomToHeight } from '@/utils/coordinate'

const emit = defineEmits<{
  'coordinate-picked': [coordinate: { lon: number; lat: number }]
}>()
const mapStore = useMapStore()
const layerStore = useLayerStore()
const workbenchStore = useWorkbenchStore()
const containerRef = ref<HTMLDivElement | null>(null)

let viewer: Viewer | null = null
let eventHandler: ScreenSpaceEventHandler | null = null
let farmlandDataSource: GeoJsonDataSource | null = null
let boundaryDataSource: GeoJsonDataSource | null = null
let tileset: Cesium3DTileset | null = null

const loadVisiblePlots = (): void => {
  if (!viewer || viewer.isDestroyed() || mapStore.viewTypeRef !== '3d') return
  const rectangle = viewer.camera.computeViewRectangle(
    viewer.scene.globe.ellipsoid,
  )
  if (!rectangle) return
  void workbenchStore.loadPlotsForViewport(
    {
      min_lon: CesiumMath.toDegrees(rectangle.west),
      min_lat: CesiumMath.toDegrees(rectangle.south),
      max_lon: CesiumMath.toDegrees(rectangle.east),
      max_lat: CesiumMath.toDegrees(rectangle.north),
    },
    heightToZoom(viewer.camera.positionCartographic.height),
  )
}

const getLandClassColor = (landClass: string | undefined): Color => ({
  耕地: Color.fromCssColorString('#d9a62e'),
  园地: Color.fromCssColorString('#4f9655'),
  林地: Color.fromCssColorString('#2f7048'),
  草地: Color.fromCssColorString('#4c9b82'),
  水域: Color.fromCssColorString('#3b89bf'),
  建设用地: Color.fromCssColorString('#8b7062'),
})[landClass || ''] || Color.fromCssColorString('#d9a62e')

/**
 * 加载后端返回的 WGS84 GeoJSON 并应用图斑样式。
 * Args:
 *   无。
 * Returns:
 *   Promise<void>: 图层刷新完成后结束。
 */
const refreshFeatures = async (): Promise<void> => {
  if (!viewer || viewer.isDestroyed()) return
  if (farmlandDataSource) {
    viewer.dataSources.remove(farmlandDataSource, true)
    farmlandDataSource = null
  }
  if (!layerStore.farmlandFeaturesRef?.features?.length) return

  farmlandDataSource = await GeoJsonDataSource.load(layerStore.farmlandFeaturesRef, {
    clampToGround: false,
    fill: Color.fromCssColorString('#d9a62e').withAlpha(0.34),
    stroke: Color.fromCssColorString('#f4cb63'),
    strokeWidth: 3,
  })
  const farmlandLayer = layerStore.layersRef.find((layer) => layer.key === 'farmland')
  farmlandDataSource.show = farmlandLayer?.visible ?? true
  viewer.dataSources.add(farmlandDataSource)
  applyEntityStyles()
}

const applyEntityStyles = (): void => {
  if (!farmlandDataSource) return
  const selectedCode = mapStore.selectedPlotRef?.plot_code
  farmlandDataSource.entities.values.forEach((entity) => {
    if (!entity.polygon) return
    const code = entity.properties?.plot_code?.getValue()
    const landClass = entity.properties?.land_class?.getValue() as string | undefined
    const landClassColor = getLandClassColor(landClass)
    const selected = code === selectedCode
    entity.polygon.height = new ConstantProperty(0)
    entity.polygon.extrudedHeight = new ConstantProperty(selected ? 450 : 220)
    entity.polygon.material = new ColorMaterialProperty(selected
      ? Color.fromCssColorString('#e6482f').withAlpha(0.48)
      : landClassColor.withAlpha(0.34))
    entity.polygon.outline = new ConstantProperty(true)
    entity.polygon.outlineColor = new ConstantProperty(selected
      ? Color.fromCssColorString('#ffdfd8')
      : landClassColor.brighten(0.25, new Color()))
  })
}

/**
 * 加载省、市、县区三级真实行政边界，三维模式只显示边线不遮挡影像。
 * Args:
 *   无。
 * Returns:
 *   Promise<void>: 行政边界刷新完成后结束。
 */
const refreshBoundaryFeatures = async (): Promise<void> => {
  if (!viewer || viewer.isDestroyed()) return
  if (boundaryDataSource) {
    viewer.dataSources.remove(boundaryDataSource, true)
    boundaryDataSource = null
  }
  if (!layerStore.boundaryFeaturesRef?.features?.length) return
  boundaryDataSource = await GeoJsonDataSource.load(
    layerStore.boundaryFeaturesRef,
    {
      clampToGround: false,
      fill: Color.TRANSPARENT,
      stroke: Color.fromCssColorString('#75c9ef'),
      strokeWidth: 2,
    },
  )
  const boundaryLayer = layerStore.layersRef.find(
    (layer) => layer.key === 'boundary',
  )
  boundaryDataSource.show = boundaryLayer?.visible ?? true
  boundaryDataSource.entities.values.forEach((entity) => {
    if (!entity.polygon) return
    const level = entity.properties?.boundary_level?.getValue()
    const color = level === 'province'
      ? Color.fromCssColorString('#2da9e6')
      : level === 'city'
        ? Color.fromCssColorString('#6bc7ef')
        : Color.fromCssColorString('#b6e7f8')
    entity.polygon.height = new ConstantProperty(10)
    entity.polygon.material = new ColorMaterialProperty(Color.TRANSPARENT)
    entity.polygon.outline = new ConstantProperty(true)
    entity.polygon.outlineColor = new ConstantProperty(color)
  })
  viewer.dataSources.add(boundaryDataSource)
}

const updateLayerState = (): void => {
  if (!viewer) return
  const base = layerStore.layersRef.find((layer) => layer.key === 'base')
  const farmland = layerStore.layersRef.find((layer) => layer.key === 'farmland')
  const boundary = layerStore.layersRef.find((layer) => layer.key === 'boundary')
  const imageryLayer = viewer.imageryLayers.get(0)
  if (imageryLayer) {
    imageryLayer.show = base?.visible ?? true
    imageryLayer.alpha = (base?.opacity ?? 100) / 100
  }
  if (farmlandDataSource) {
    farmlandDataSource.show = farmland?.visible ?? true
    farmlandDataSource.entities.values.forEach((entity) => {
      if (entity.polygon) {
        const alpha = ((farmland?.opacity ?? 82) / 100) * 0.48
        const selected = entity.properties?.plot_code?.getValue()
          === mapStore.selectedPlotRef?.plot_code
        const landClass = entity.properties?.land_class?.getValue() as string | undefined
        const landClassColor = getLandClassColor(landClass)
        entity.polygon.material = new ColorMaterialProperty(selected
          ? Color.fromCssColorString('#e6482f').withAlpha(alpha)
          : landClassColor.withAlpha(alpha))
      }
    })
  }
  if (boundaryDataSource) {
    boundaryDataSource.show = boundary?.visible ?? true
  }
}

/**
 * 加载可选的生产级 3D Tiles 数据集。
 * Args:
 *   url: 3D Tiles 服务地址。
 * Returns:
 *   Promise<void>: 瓦片集加入场景后结束。
 */
const loadTiles = async (url: string | undefined): Promise<void> => {
  if (!url || !viewer) return
  tileset = await Cesium3DTileset.fromUrl(url)
  // 业务硬性要求：3D Tiles 的最大屏幕空间误差固定为 2。
  tileset.maximumScreenSpaceError = 2
  viewer.scene.primitives.add(tileset)
}

/**
 * 初始化 Cesium Viewer、OSM 底图、点击拾取和相机监听。
 * Args:
 *   无。
 * Returns:
 *   Promise<void>: 三维视图初始化完成后结束。
 */
const initializeViewer = async (): Promise<void> => {
  if (!containerRef.value) return
  viewer = new Viewer(containerRef.value, {
    animation: false,
    timeline: false,
    geocoder: false,
    homeButton: false,
    sceneModePicker: false,
    baseLayerPicker: false,
    navigationHelpButton: false,
    fullscreenButton: false,
    infoBox: false,
    selectionIndicator: false,
    baseLayer: false,
    requestRenderMode: true,
    maximumRenderTimeChange: Number.POSITIVE_INFINITY,
  })
  const activeViewer = viewer
  activeViewer.imageryLayers.addImageryProvider(
    new UrlTemplateImageryProvider({
      url: `${window.location.origin}/imagery-tiles/{z}/{y}/{x}`,
      credit: 'Imagery © Esri, Maxar, Earthstar Geographics',
    }),
  )
  activeViewer.scene.globe.depthTestAgainstTerrain = false
  activeViewer.scene.globe.enableLighting = false
  activeViewer.clock.shouldAnimate = false
  activeViewer.scene.screenSpaceCameraController.inertiaSpin = 0
  activeViewer.scene.screenSpaceCameraController.inertiaTranslate = 0
  activeViewer.scene.screenSpaceCameraController.inertiaZoom = 0
  // 保留用户主动交互，但关闭释放鼠标后的惯性漂移。
  activeViewer.scene.screenSpaceCameraController.enableInputs = true
  setCurrentCameraView()

  eventHandler = new ScreenSpaceEventHandler(activeViewer.scene.canvas)
  eventHandler.setInputAction((movement: { position: Cartesian2 }) => {
    const cartesian = activeViewer.camera.pickEllipsoid(
      movement.position,
      activeViewer.scene.globe.ellipsoid,
    )
    if (!cartesian) return
    const cartographic = activeViewer.scene.globe.ellipsoid
      .cartesianToCartographic(cartesian)
    emit('coordinate-picked', {
      lon: CesiumMath.toDegrees(cartographic.longitude),
      lat: CesiumMath.toDegrees(cartographic.latitude),
    })
  }, ScreenSpaceEventType.LEFT_CLICK)

  activeViewer.camera.moveEnd.addEventListener(() => {
    if (mapStore.viewTypeRef !== '3d') return
    const centerCartesian = activeViewer.camera.pickEllipsoid(
      new Cartesian2(
        activeViewer.canvas.clientWidth / 2,
        activeViewer.canvas.clientHeight / 2,
      ),
    )
    if (!centerCartesian) return
    const cartographic = activeViewer.scene.globe.ellipsoid
      .cartesianToCartographic(centerCartesian)
    mapStore.updateView(
      [
        CesiumMath.toDegrees(cartographic.longitude),
        CesiumMath.toDegrees(cartographic.latitude),
      ],
      heightToZoom(activeViewer.camera.positionCartographic.height),
    )
    loadVisiblePlots()
  })

  await Promise.all([
    refreshFeatures(),
    refreshBoundaryFeatures(),
    loadTiles(import.meta.env.VITE_CESIUM_3D_TILES_URL),
  ])
  updateLayerState()
  loadVisiblePlots()
}

const getCameraTarget = (): Cartesian3 => Cartesian3.fromDegrees(
  mapStore.centerRef[0],
  mapStore.centerRef[1],
  0,
)

const getCameraOffset = (): HeadingPitchRange => new HeadingPitchRange(
  CesiumMath.toRadians(0),
  CesiumMath.toRadians(-60),
  zoomToHeight(mapStore.zoomRef) * 1.2,
)

const setCurrentCameraView = (): void => {
  if (!viewer || viewer.isDestroyed()) return
  viewer.camera.lookAt(getCameraTarget(), getCameraOffset())
  viewer.camera.lookAtTransform(Matrix4.IDENTITY)
}

/**
 * 刷新三维图斑，不改变固定相机视角。
 * Args:
 *   feature: GeoJSON Feature。
 * Returns:
 *   void: 无返回值。
 */
const flyToFeature = (feature: GeoJsonFeature): void => {
  if (!viewer || !feature) return
  viewer.scene.requestRender()
}

const clearSelection = (): void => {
  applyEntityStyles()
}

watch(
  () => layerStore.farmlandFeaturesRef,
  () => {
    void refreshFeatures()
  },
  { deep: true },
)

watch(
  () => layerStore.layersRef,
  updateLayerState,
  { deep: true },
)

watch(
  () => layerStore.boundaryFeaturesRef,
  () => {
    void refreshBoundaryFeatures()
  },
  { deep: true },
)

watch(
  () => mapStore.selectedPlotRef,
  applyEntityStyles,
  { deep: true },
)

watch(
  () => mapStore.focusRequestRef,
  (request) => {
    if (!request || !viewer || mapStore.viewTypeRef !== '3d') return
    const [west, south, east, north] = request.extent
    // 仅响应用户点击行政层级，直接定位且不启动飞行动画。
    viewer.camera.setView({
      destination: Rectangle.fromDegrees(west, south, east, north),
    })
    viewer.scene.requestRender()
  },
  { deep: true },
)

onMounted(() => {
  void initializeViewer()
})

const destroyViewer = (): void => {
  if (eventHandler && !eventHandler.isDestroyed()) eventHandler.destroy()
  if (viewer && !viewer.isDestroyed()) viewer.destroy()
  eventHandler = null
  viewer = null
}

onBeforeUnmount(destroyViewer)

if (import.meta.hot) {
  import.meta.hot.dispose(destroyViewer)
}

defineExpose({ viewer, flyToFeature, clearSelection })
</script>

<template>
  <div ref="containerRef" class="cesium-map" />
</template>

<style scoped>
.cesium-map {
  width: 100%;
  height: 100%;
}
</style>
