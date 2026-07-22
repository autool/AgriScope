import type { GeoJsonFeature } from '@/types/workbench'

export type GeoJsonExtent = [number, number, number, number]

const extendCoordinateExtent = (
  extent: GeoJsonExtent,
  value: unknown,
): void => {
  if (!Array.isArray(value)) return
  if (
    value.length >= 2
    && typeof value[0] === 'number'
    && typeof value[1] === 'number'
  ) {
    extent[0] = Math.min(extent[0], value[0])
    extent[1] = Math.min(extent[1], value[1])
    extent[2] = Math.max(extent[2], value[0])
    extent[3] = Math.max(extent[3], value[1])
    return
  }
  value.forEach((item) => extendCoordinateExtent(extent, item))
}

/**
 * 计算 WGS84 GeoJSON Feature 的经纬度范围。
 * Args:
 *   feature: 任意坐标嵌套层级的 GeoJSON Feature。
 * Returns:
 *   GeoJsonExtent | null: 有效包围盒；无坐标时返回 null。
 */
export const getGeoJsonFeatureExtent = (
  feature: GeoJsonFeature,
): GeoJsonExtent | null => {
  const extent: GeoJsonExtent = [Infinity, Infinity, -Infinity, -Infinity]
  extendCoordinateExtent(extent, feature.geometry.coordinates)
  return extent.every(Number.isFinite) ? extent : null
}
