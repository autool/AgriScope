const EARTH_CIRCUMFERENCE = 40075016.686

/**
 * 将 OpenLayers 缩放级别近似转换为 Cesium 相机高度。
 * @param {number} zoom 二维地图缩放级别。
 * @returns {number} 三维相机高度（米）。
 */
export const zoomToHeight = (zoom: number): number =>
  EARTH_CIRCUMFERENCE / 2 ** Math.max(zoom - 1, 0)

/**
 * 将 Cesium 相机高度近似转换为 OpenLayers 缩放级别。
 * @param {number} height 三维相机高度（米）。
 * @returns {number} 二维地图缩放级别。
 */
export const heightToZoom = (height: number): number =>
  Math.max(2, Math.min(20, Math.log2(EARTH_CIRCUMFERENCE / height) + 1))

/**
 * 限制经纬度到 WGS84 有效范围。
 * @param {number[]} center 中心经纬度。
 * @returns {number[]} 安全的中心点。
 */
export const clampWgs84Center = ([lon, lat]: [number, number]): [number, number] => [
  Math.max(-180, Math.min(180, lon)),
  Math.max(-90, Math.min(90, lat)),
]
